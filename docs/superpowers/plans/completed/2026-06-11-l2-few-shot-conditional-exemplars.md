# L2 Few-Shot Conditional Exemplars Implementation Plan

Introduce structured few-shot examples into the system prompt to guide the LLM (specifically Llama-3.3-70B) in preserving the condition→branch structure of agronomic advisories (rates by soil texture, thresholds by crop stage, variety restrictions).

## Problem & Background

Under the honest 70B production baseline evaluation, the overall correctness rate is 20%-22%. The main bottleneck is that the generation LLM collapses multi-branch conditional rules (e.g. stink bug threshold changing by week after heading, herbicide rates by soil texture) into bare numbers or singular values, stripping the farmer of the qualifying context.

The previous prompt directive (L1) was measured as a **no-op** (`conditional_completeness_rate` remained at `0.429` on the 7-row conditional gold subset). Adding output instructions is insufficient for larger models under strict structured schemas. We need to introduce two concrete, worked-out JSON examples (few-shot exemplars) into the system prompt to demonstrate the required structure and preservation of conditional branches.

## Proposed Changes

### [Component: Backend Utilities]

#### [MODIFY] [prompt.py](file:///c:/Users/jeged/Downloads/AgroAdvisor/backend/utils/prompt.py)
* Add a `FEW_SHOT_EXEMPLARS` block defining two worked examples:
  1. **Example 1 (Soil Texture Rate Rule):** Command 3ME rate split by soil texture (coarse: 1.2 pt/A, medium: 1.6 pt/A, fine: 2.0 pt/A, prohibit on sand). Shows mapping to multiple entries in `products_rates` and explicit conditions in `key_points`.
  2. **Example 2 (Crop Stage / Timing Threshold Rule):** Grape colaspis pre-flood (5 larvae/sq ft) and post-flood (not recommended) rule. Shows how to preserve timing conditions and limitations in `key_points` and `recommended_actions`.
* Append `FEW_SHOT_EXEMPLARS` inside `build_system_prompt` after the output instructions.

#### [MODIFY] [test_prompt.py](file:///c:/Users/jeged/Downloads/AgroAdvisor/backend/tests/test_prompt.py)
* Add a test `test_few_shot_exemplars_present_in_prompt()` asserting `FEW_SHOT_EXEMPLARS` is present in the assembled system prompt for both diagnostic and informational intents.

---

## Verification Plan

### Automated Tests
* Run prompt unit tests:
  ```bash
  cd backend && pytest tests/test_prompt.py -v
  ```
* Run the full backend test suite to check for schema/deserialization regressions:
  ```bash
  pytest backend/tests
  ```

### Manual/Measurement Verification
* Run the conditional-only subset of the diagnostic runner using DeepInfra Llama-3.3-70B as primary:
  ```bash
  python -m evals.diagnostic.runner --gold evals/diagnostic/gold_conditional.jsonl
  ```
* Measure the `conditional_completeness_rate` and `conditional_scored_n` output. Verify if it improves over the `0.429` baseline (we want to see the rate lift towards `1.0`).
