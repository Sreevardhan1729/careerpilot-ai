import { asArray, asNumber, asRecord, asString } from "@/lib/utils";
import type { ResumeEducation, ResumeExperience, ResumeParsed, ResumeProject, ResumeSkill } from "@/types/models";

/** ResumeParsed with every list present (the generated type marks defaulted fields optional). */
export type EditableParsed = Omit<
  ResumeParsed,
  "contact" | "skills" | "experience" | "projects" | "education" | "certifications" | "achievements" | "domains" | "section_order"
> & {
  contact: NonNullable<ResumeParsed["contact"]>;
  skills: ResumeSkill[];
  experience: ResumeExperience[];
  projects: ResumeProject[];
  education: ResumeEducation[];
  certifications: string[];
  achievements: NonNullable<ResumeParsed["achievements"]>;
  domains: string[];
  section_order: string[];
};

const strList = (v: unknown) => asArray(v).map((x) => asString(x)).filter((x): x is string => !!x);

export function emptyExperience(): ResumeExperience {
  return { title: null, company: null, start: null, end: null, months: null, is_internship: false, bullets: [], technologies: [], domains: [] };
}

export function emptyProject(): ResumeProject {
  return { title: null, description: null, bullets: [], technologies: [], domains: [], links: [] };
}

export function emptyEducation(): ResumeEducation {
  return { degree: null, institution: null, year: null, details: null };
}

export function emptySkill(): ResumeSkill {
  return { name: "", section: "skills", evidence: null };
}

/** Turns the stored `parsed_data` dict into a complete ResumeParsed (the PUT body must be the full object). */
export function normalizeParsed(raw: unknown): EditableParsed {
  const p = asRecord(raw);
  const c = asRecord(p.contact);
  return {
    contact: {
      name: asString(c.name),
      email: asString(c.email),
      phone: asString(c.phone),
      location: asString(c.location),
      linkedin_url: asString(c.linkedin_url),
      github_url: asString(c.github_url),
      portfolio_url: asString(c.portfolio_url),
    },
    summary: asString(p.summary),
    skills: asArray(p.skills).map((s) => {
      const r = asRecord(s);
      return { name: asString(r.name) ?? "", section: asString(r.section) ?? "skills", evidence: asString(r.evidence) };
    }),
    experience: asArray(p.experience).map((e) => {
      const r = asRecord(e);
      return {
        title: asString(r.title),
        company: asString(r.company),
        start: asString(r.start),
        end: asString(r.end),
        months: asNumber(r.months),
        is_internship: r.is_internship === true,
        bullets: strList(r.bullets),
        technologies: strList(r.technologies),
        domains: strList(r.domains),
      };
    }),
    projects: asArray(p.projects).map((e) => {
      const r = asRecord(e);
      return {
        title: asString(r.title),
        description: asString(r.description),
        bullets: strList(r.bullets),
        technologies: strList(r.technologies),
        domains: strList(r.domains),
        links: strList(r.links),
      };
    }),
    education: asArray(p.education).map((e) => {
      const r = asRecord(e);
      return { degree: asString(r.degree), institution: asString(r.institution), year: asString(r.year), details: asString(r.details) };
    }),
    certifications: strList(p.certifications),
    achievements: asArray(p.achievements)
      .map((a) => {
        const r = asRecord(a);
        const text = asString(r.text) ?? asString(a);
        return text ? { text, metric: asString(r.metric) } : null;
      })
      .filter((a): a is { text: string; metric: string | null } => a !== null),
    domains: strList(p.domains),
    section_order: strList(p.section_order),
  };
}

/** Drop blank rows and trim before saving. */
export function cleanParsed(p: EditableParsed): EditableParsed {
  const t = (s: string | null | undefined) => (s && s.trim() ? s.trim() : null);
  const list = (xs: string[] | undefined) => (xs ?? []).map((x) => x.trim()).filter(Boolean);
  return {
    ...p,
    summary: t(p.summary),
    skills: p.skills.filter((s) => s.name.trim()).map((s) => ({ ...s, name: s.name.trim(), evidence: t(s.evidence) })),
    experience: p.experience
      .filter((e) => t(e.title) || t(e.company))
      .map((e) => ({ ...e, title: t(e.title), company: t(e.company), start: t(e.start), end: t(e.end), bullets: list(e.bullets), technologies: list(e.technologies) })),
    projects: p.projects
      .filter((e) => t(e.title) || t(e.description))
      .map((e) => ({ ...e, title: t(e.title), description: t(e.description), bullets: list(e.bullets), technologies: list(e.technologies), links: list(e.links) })),
    education: p.education
      .filter((e) => t(e.degree) || t(e.institution))
      .map((e) => ({ degree: t(e.degree), institution: t(e.institution), year: t(e.year), details: t(e.details) })),
    certifications: list(p.certifications),
  };
}
