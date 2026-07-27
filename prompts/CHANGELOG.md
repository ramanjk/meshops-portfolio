# Prompt CHANGELOG

## 1.1.0
- `inference-steward.chat.md`: strengthened identity anchoring for the small
  chat model (phi-4-mini). Added a non-negotiable **Identity** section so the
  steward always self-identifies as the "Inference Steward" and never as a
  generic AI assistant / language model, including a canonical self-intro line
  and a rule for "what model are you" questions.

## 1.0.0
- Initial system prompt for `hello-inference` (iteration-01).
- Read-only stance; no `proposed_actions`; `requires_hitl` forced false.
