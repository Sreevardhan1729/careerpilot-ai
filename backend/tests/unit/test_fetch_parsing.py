import io
import zipfile

import docx
import httpx
import pymupdf
import pytest

from app.core.errors import (
    FetchFailed,
    FileTooLarge,
    SourceNotPermitted,
    UnsafeUrl,
    UnsupportedFileType,
    ValidationFailed,
)
from app.integrations.fetch import SafeFetcher
from app.integrations.parsing.documents import extract_document, validate_upload
from app.integrations.parsing.html import extract_jsonld_jobposting, html_to_text


def fetcher(handler=None, ips=("93.184.216.34",)):
    async def resolver(host):
        return list(ips)

    transport = httpx.MockTransport(handler) if handler else None
    return SafeFetcher(resolver=resolver, transport=transport, pin_ips=False, min_interval=0)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
                                "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1"])
async def test_rejects_non_public_addresses(ip):
    with pytest.raises(UnsafeUrl):
        await fetcher(ips=(ip,)).validate_target("https://example.com/jobs")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/", "http://example.com:8080/"])
async def test_rejects_bad_schemes_credentials_ports(url):
    with pytest.raises(UnsafeUrl):
        await fetcher().validate_target(url)


async def test_blocked_hosts_are_not_permitted():
    with pytest.raises(SourceNotPermitted) as exc:
        await fetcher().get("https://www.linkedin.com/jobs/view/123")
    assert exc.value.details["suggestion"] == "paste_text"


async def test_redirect_to_private_address_is_blocked():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://internal.local/admin"})

    async def resolver(host):
        return ["10.0.0.1"] if host == "internal.local" else ["93.184.216.34"]

    f = SafeFetcher(resolver=resolver, transport=httpx.MockTransport(handler), pin_ips=False, min_interval=0)
    with pytest.raises(UnsafeUrl):
        await f.get("https://example.com/job")


async def test_oversize_body_rejected_and_content_type_checked():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/big":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 5000)
        return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"bin")

    f = fetcher(handler)
    f.max_bytes = 1000
    with pytest.raises(FetchFailed):
        await f.get("https://example.com/big")
    with pytest.raises(FetchFailed):
        await f.get("https://example.com/binary")


async def test_robots_disallow_is_respected_and_ua_sent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><body>ok</body></html>")

    f = fetcher(handler)
    assert (await f.get("https://example.com/public")).text.endswith("</html>")
    assert "CareerPilotBot" in seen["ua"]
    with pytest.raises(SourceNotPermitted):
        await f.get("https://example.com/private/page")


def test_html_to_text_strips_chrome_and_keeps_structure():
    html = """<html><head><title>AI Engineer</title><script>alert(1)</script></head>
    <body><nav>Home Jobs</nav><h1>AI Engineer</h1><ul><li>Python</li><li>RAG</li></ul><footer>©</footer></body></html>"""
    title, text = html_to_text(html)
    assert title == "AI Engineer"
    assert "alert" not in text and "Home Jobs" not in text
    assert "- Python" in text and "- RAG" in text


def test_jsonld_jobposting_extraction():
    html = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"ML Engineer",
    "hiringOrganization":{"@type":"Organization","name":"Acme"},"datePosted":"2026-11-10","description":"<p>Build <b>models</b></p>",
    "jobLocation":{"@type":"Place","address":{"addressLocality":"Pune","addressCountry":"IN"}},
    "baseSalary":{"@type":"MonetaryAmount","currency":"INR","value":{"minValue":1000000,"maxValue":1500000,"unitText":"YEAR"}}}</script>"""
    jp = extract_jsonld_jobposting(html)
    assert jp["title"] == "ML Engineer" and jp["company"] == "Acme" and jp["location"] == "Pune, IN"
    assert jp["description"] == "Build models"
    assert jp["salary"] == {"minimum": 1000000, "maximum": 1500000, "currency": "INR", "period": "annual"}


def _docx_bytes(text="Hello resume"):
    d = docx.Document()
    d.add_heading("Skills", level=1)
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _pdf_bytes(pages=1, encrypt=False):
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Page {i + 1} Python FastAPI")
    kw = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": "x", "owner_pw": "y"} if encrypt else {}
    return doc.tobytes(**kw)


def test_validate_upload_accepts_pdf_and_docx_by_magic_bytes():
    assert validate_upload(_pdf_bytes(), max_mb=5, max_pages=20).kind == "pdf"
    assert validate_upload(_docx_bytes(), max_mb=5, max_pages=20).kind == "docx"


def test_validate_upload_rejects_wrong_type_size_macros_bombs_encryption_pages():
    with pytest.raises(UnsupportedFileType):
        validate_upload(b"MZ\x90\x00not a pdf", max_mb=5, max_pages=20)
    with pytest.raises(FileTooLarge):
        validate_upload(b"%PDF-" + b"0" * (2 * 1024 * 1024), max_mb=1, max_pages=20)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_docx_bytes())) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        dst.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(UnsupportedFileType):
        validate_upload(buf.getvalue(), max_mb=5, max_pages=20)
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "a" * (60 * 1024 * 1024))
    with pytest.raises(ValidationFailed):
        validate_upload(bomb.getvalue(), max_mb=5, max_pages=20)
    with pytest.raises(ValidationFailed):
        validate_upload(_pdf_bytes(encrypt=True), max_mb=5, max_pages=20)
    with pytest.raises(ValidationFailed):
        validate_upload(_pdf_bytes(pages=3), max_mb=5, max_pages=2)


def test_extract_document_text():
    pdf = extract_document(_pdf_bytes(pages=2), "pdf")
    assert pdf.page_count == 2 and "Python FastAPI" in pdf.text
    d = extract_document(_docx_bytes("Python, FastAPI"), "docx")
    assert "Skills" in d.text and "Python, FastAPI" in d.text
