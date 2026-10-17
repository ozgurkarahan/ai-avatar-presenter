# AI enablement series — sources

Consolidated references for the four decks in this folder. Speaker notes were
fact-checked against these pages (first-party specifications and documentation
where available) when the series was written in 2026.

**Slide keys:** `B` = Beginner (*AI, Demystified*), `P` = Practitioner
(*Building with AI*), `E` = Expert (*Under the Hood*), `Demo` = Beginner demo
cut. The number is the slide number in that deck (for example `P6` is slide 6
of `ai-enablement-2-practitioner.pptx`).

| # | Source | URL | What it supports | Slides |
|---|---|---|---|---|
| 1 | Model Context Protocol — "Introduction" | <https://modelcontextprotocol.io/introduction> | What MCP is; the host/application-to-tool "universal connector" analogy. | B7, B11 |
| 2 | Model Context Protocol — "Architecture overview" | <https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture> | Host/client/server roles, data vs. transport layers, tools/resources/prompts primitives, stdio vs. streamable HTTP. | P5, P6, P9 |
| 3 | Model Context Protocol — "Security Best Practices" | <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices> | Confused deputy problem, token/consent handling, least-privilege guidance for MCP implementations. | E9, E10 |
| 4 | Model Context Protocol — "Authorization specification" | <https://modelcontextprotocol.io/specification/latest/basic/authorization> | OAuth 2.1-based authorization flow, protected resource metadata, stdio vs. HTTP authorization requirements. | P6, E9 |
| 5 | Open Source Initiative — "The Open Source AI Definition 1.0" | <https://opensource.org/ai/open-source-ai-definition> | Formal definition of Open Source AI; required data/code/parameter disclosures; model vs. weights terminology. | B9, P2, E6 |
| 6 | Open Source Initiative — "Open Source AI Definition FAQ" | <https://opensource.org/ai/faq> | OECD AI system definition; clarifies that open-weight availability alone does not equal Open Source AI. | B2, B9, E6, Demo 2 |
| 7 | Vaswani, A. et al. — "Attention Is All You Need" (2017) | <https://arxiv.org/abs/1706.03762> | Transformer architecture and self-attention mechanism underlying modern language models. | E1, E2 |
| 8 | Liu, N. F. et al. — "Lost in the Middle: How Language Models Use Long Contexts" (2023) | <https://arxiv.org/abs/2307.03172> | Finding that relevant information positioned in the middle of long contexts is retrieved less reliably. | E3 |
| 9 | Anthropic — "Building Effective Agents" | <https://www.anthropic.com/engineering/building-effective-agents> | Distinction between workflows and agents; the augmented-LLM building block; planner/sub-agent patterns; start-simple guidance. | B6, B11, B12, P4, P9, E7, E8, Demo 3, Demo 5 |
| 10 | Microsoft Learn — "Understanding tokens" | <https://learn.microsoft.com/en-us/dotnet/ai/conceptual/understanding-tokens> | Tokenization methods (word, character, subword), vocabulary, and how models assign and use token IDs. | B5, P3, E2 |
| 11 | Microsoft Learn — "Concepts: Small and large language models" | <https://learn.microsoft.com/en-us/azure/aks/concepts-ai-ml-language-models> | General distinction and trade-offs between small and large language models. | B3, P2 |
| 12 | Microsoft Learn — "What is Microsoft Foundry Agent Service?" | <https://learn.microsoft.com/en-us/azure/foundry/agents/overview> | Agent runtime, toolboxes/MCP integration, model swapping, observability, identity and security features of a managed agent platform. | P1, P4, P8, P10, P11, P12, E8 |
| 13 | Microsoft Learn — "RAG and Generative AI - Azure AI Search" | <https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview> | Retrieval-augmented generation pattern, its challenges (token limits, security, relevance), and agentic vs. classic RAG. | P3 |
| 14 | Microsoft Learn — "Text to speech overview" | <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech> | Neural text-to-speech synthesis; standard and custom voices. | B8, P7, Demo 4 |
| 15 | Microsoft Learn — "Speech to text overview" | <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text> | Real-time, fast, and batch transcription; custom speech. | B8 |
| 16 | Microsoft Learn — "Voice Live API overview" | <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live> | Unified, fully managed speech-to-speech architecture; chained vs. realtime trade-off; avatar and voice-agent use cases. | B8, P7, P11, E11, Demo 1, Demo 4 |
| 17 | Microsoft Learn — "Handle voice interruptions in chat history" (Voice Live auto-truncation) | <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-voice-live-auto-truncation> | Barge-in, auto-truncation, and voice activity detection configuration for interruption handling. | E11 |
| 18 | Microsoft Learn — "What is Foundry Local?" | <https://learn.microsoft.com/en-us/azure/foundry-local/what-is-foundry-local> | On-device inference runtime built on ONNX Runtime, with quantized model catalog and automatic hardware acceleration. | E5 |
| 19 | llama.cpp (ggml-org) — GitHub repository | <https://github.com/ggml-org/llama.cpp> | Local LLM/VLM inference engine; quantization bit-widths; hardware backend support (CPU, GPU, Apple Silicon, etc.). | E5 |
| 20 | Ollama — product homepage | <https://ollama.com> | Local runtime for running open models privately, without cloud dependency. | E5 |
| 21 | vLLM — documentation homepage | <https://docs.vllm.ai/en/latest/> | High-throughput LLM serving; PagedAttention; supported quantization formats. | E5 |
| 22 | National Institute of Standards and Technology — "AI Risk Management Framework" | <https://www.nist.gov/itl/ai-risk-management-framework> | Voluntary framework (Govern/Map/Measure/Manage) for managing AI risk. | E12 |
| 23 | OWASP GenAI Security Project — "LLM01:2025 Prompt Injection" | <https://genai.owasp.org/llmrisk/llm01-prompt-injection/> | Direct vs. indirect prompt injection definitions and recommended mitigations, including least privilege. | P10, E10 |
| 24 | Microsoft — "Responsible AI principles and approach" | <https://www.microsoft.com/en-us/ai/principles-and-approach> | Published responsible AI principles and a real risk-mapping example (prompt injection, red-teaming) for a shipped feature. | B1, B10, E12 |
| 25 | Microsoft Learn — "Microsoft Foundry reasoning models" | <https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-chat-reasoning> | Definition of reasoning models as using extra computation to solve complex problems before answering. | B4, E4 |

## Notes

- **Diagrams are original.** Every diagram is drawn with native, editable
  PowerPoint shapes by `scripts/generate_ai_enablement_pptx.py`. No third-party
  images, logos or icon packs are used, and no diagram is copied from a source.
  Illustrative charts (the attention matrix, the "lost in the middle" curve and
  the model-choice grid) show a qualitative shape, not measured data.
- **Model and product names are examples as of 2026.** Model families named in
  the notes (a GPT-4.1-class frontier model, the Phi family of small models,
  the Llama and Mistral families of open-weight models) and runtimes
  (llama.cpp, Ollama, vLLM, ONNX Runtime / Foundry Local, Voice Live) are
  illustrative, generic examples. They are not benchmark, ranking, availability
  or "latest/best" claims; check current documentation and licence terms before
  relying on them.
- No specific benchmark scores, parameter counts or prices are quoted.
- "Open-weight" is deliberately distinguished from "Open Source AI", following
  the Open Source Initiative definition and FAQ (sources 5 and 6).
- URLs are kept out of the speaker notes so the avatar never reads them aloud.
