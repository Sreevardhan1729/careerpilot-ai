/** True when a value came from the deterministic rule-based pipeline rather than an LLM. */
export function isRuleBased(analysisMethod: string | null | undefined, modelId: string | null | undefined): boolean {
  if (!modelId) return true;
  return /^heuristic/i.test(modelId) || /heuristic|rule/i.test(analysisMethod ?? "");
}
