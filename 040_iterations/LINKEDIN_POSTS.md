# MeshOps — LinkedIn Post Series

LinkedIn strips markdown, but keeps line breaks, emojis, Unicode bold and divider
characters. These versions are formatted with those so they render scannable and
attractive. Copy the block between the >>> markers straight into the LinkedIn box.

Attach the media from 040_iterations/assets/ :
- Post #1  ->  meshops-arch.mp4 (video)  or  meshops-arch.png (image)
- Posts #2/#3 -> reuse the diagram or a per-steward visual

============================================================
POST #1 — PROJECT INTRO
============================================================
>>>
𝗥𝘂𝗻𝗻𝗶𝗻𝗴 𝗮𝗻 𝗔𝗜 𝗽𝗹𝗮𝘁𝗳𝗼𝗿𝗺 𝗶𝘀𝗻'𝘁 𝗼𝗻𝗲 𝗷𝗼𝗯. 𝗜𝘁'𝘀 𝗳𝗼𝘂𝗿. 😵‍💫

It's 2 a.m. Your LLM platform on Kubernetes is misbehaving:

📈  latency is doubling
🔁  a fine-tune is queued for promotion
📚  the RAG corpus just changed
🖥️  the GPU pool is maxing out

Four specialties — 𝗟𝗟𝗠𝗢𝗽𝘀 · 𝗠𝗟𝗢𝗽𝘀 · 𝗔𝗜𝗢𝗽𝘀 · 𝗦𝗲𝗰𝗢𝗽𝘀 — braided together for one tired on-call human.

━━━━━━━━━━━━━━━━━━━━

Service mesh solved a version of this for microservices: it lifted routing, retries and security into a shared plane.

So I asked 👉 𝘄𝗵𝗮𝘁 𝗶𝗳 𝘆𝗼𝘂 𝗮𝗽𝗽𝗹𝘆 𝘁𝗵𝗮𝘁 𝘀𝗮𝗺𝗲 𝗽𝗮𝘁𝘁𝗲𝗿𝗻 𝘁𝗼 𝗼𝗽𝗲𝗿𝗮𝘁𝗶𝗼𝗻𝘀?

━━━━━━━━━━━━━━━━━━━━

𝗠𝗲𝗲𝘁 𝗠𝗲𝘀𝗵𝗢𝗽𝘀 — a mesh of small, read-only AI 𝘀𝘁𝗲𝘄𝗮𝗿𝗱 𝗮𝗴𝗲𝗻𝘁𝘀, one per operational concern.

Each steward:
🔍  observes live cluster state
🧠  reasons over what it sees
📝  proposes a fix

The rule I'm proudest of 👇
✋  𝗦𝘁𝗲𝘄𝗮𝗿𝗱𝘀 𝗽𝗿𝗼𝗽𝗼𝘀𝗲. 𝗛𝘂𝗺𝗮𝗻𝘀 𝗱𝗶𝘀𝗽𝗼𝘀𝗲.

They're read-only by design — nothing touches production without a human approving. Autonomy stops at the proposal layer.

━━━━━━━━━━━━━━━━━━━━

🛠️  Built on 𝗔𝗞𝗦 + 𝗔𝘇𝘂𝗿𝗲 𝗢𝗽𝗲𝗻𝗔𝗜 + 𝗠𝗖𝗣 + 𝗪𝗼𝗿𝗸𝗹𝗼𝗮𝗱 𝗜𝗱𝗲𝗻𝘁𝗶𝘁𝘆.

After 11 years in Kubernetes (Kubestronaut 🚀), this is my deliberate stretch into agentic AI + LLMOps.

2 stewards are already live. I'll introduce the first one next. 👇

#Kubernetes #AKS #LLMOps #MLOps #AIAgents #Azure #MCP #PlatformEngineering
<<<

============================================================
POST #2 — STEWARD #1: THE INFERENCE STEWARD (Iteration 1 · read-only)
============================================================
Media: attach a short screen-capture GIF of the chat UI answering 2–3 of the
questions below, OR reuse 040_iterations/assets/meshops-arch.png. A real
terminal/chat screenshot outperforms the diagram here — show it working.
>>>
𝗠𝗲𝗲𝘁 𝘁𝗵𝗲 𝗳𝗶𝗿𝘀𝘁 𝗠𝗲𝘀𝗵𝗢𝗽𝘀 𝘀𝘁𝗲𝘄𝗮𝗿𝗱: 𝘁𝗵𝗲 𝗜𝗻𝗳𝗲𝗿𝗲𝗻𝗰𝗲 𝗦𝘁𝗲𝘄𝗮𝗿𝗱. 🛰️

In my last post I introduced 𝗠𝗲𝘀𝗵𝗢𝗽𝘀 — a mesh of read-only AI agents that operate an LLM platform on AKS, one per ops concern.

Here's steward #1, live on the cluster 👇

━━━━━━━━━━━━━━━━━━━━

𝗪𝗵𝗮𝘁 𝗶𝘁 𝗱𝗼𝗲𝘀

The Inference Steward watches the 𝘀𝗲𝗿𝘃𝗶𝗻𝗴 side of the platform — a live SLM (Phi-4-mini) behind a 𝗞𝗔𝗜𝗧𝗢 𝗪𝗼𝗿𝗸𝘀𝗽𝗮𝗰𝗲 on AKS, on a real T4 GPU node.

It observes → reasons → reports. No canned answers — every reply is grounded in live cluster state.

━━━━━━━━━━━━━━━━━━━━

𝗜 𝗮𝗰𝘁𝘂𝗮𝗹𝗹𝘆 𝗶𝗻𝘁𝗲𝗿𝘃𝗶𝗲𝘄𝗲𝗱 𝗶𝘁 — 𝗿𝗲𝗮𝗹 𝗾𝘂𝗲𝘀𝘁𝗶𝗼𝗻𝘀, 𝗹𝗶𝘃𝗲 𝗮𝗻𝘀𝘄𝗲𝗿𝘀 🎙️

🗨️  "𝘞𝘩𝘢𝘵 𝘦𝘯𝘨𝘪𝘯𝘦 𝘢𝘯𝘥 𝘱𝘳𝘦𝘴𝘦𝘵 𝘪𝘴 𝘴𝘦𝘳𝘷𝘪𝘯𝘨 𝘵𝘩𝘦 𝘮𝘰𝘥𝘦𝘭?"
      → phi-4-mini-instruct on Standard_NC4as_T4_v3, 128k context.

🗨️  "𝘚𝘩𝘰𝘸 𝘵𝘩𝘦 𝘞𝘰𝘳𝘬𝘴𝘱𝘢𝘤𝘦 𝘤𝘰𝘯𝘥𝘪𝘵𝘪𝘰𝘯𝘴."
      → NodesReady ✓ ResourceReady ✓ InferenceReady ✓ — State: Ready.

🗨️  "𝘏𝘰𝘸 𝘮𝘢𝘯𝘺 𝘳𝘦𝘱𝘭𝘪𝘤𝘢𝘴 𝘢𝘳𝘦 𝘤𝘰𝘯𝘧𝘪𝘨𝘶𝘳𝘦𝘥 𝘷𝘴 𝘳𝘦𝘢𝘥𝘺?"
      → 1 configured, 1 pod ready — cross-checked against pod status.

🗨️  "𝘐𝘴 𝘵𝘩𝘦 𝘮𝘰𝘥𝘦𝘭 𝘩𝘦𝘢𝘭𝘵𝘩𝘺 𝘳𝘪𝘨𝘩𝘵 𝘯𝘰𝘸?"
      → Yes — cites the workspace name + namespace, not a vibe.

━━━━━━━━━━━━━━━━━━━━

𝗧𝗵𝗲 𝗽𝗮𝗿𝘁 𝗜'𝗺 𝗽𝗿𝗼𝘂𝗱𝗲𝘀𝘁 𝗼𝗳 — 𝗶𝘁 𝗿𝗲𝗳𝘂𝘀𝗲𝘀 𝘁𝗼 𝘄𝗿𝗶𝘁𝗲

🔒  𝗥𝗲𝗮𝗱-𝗼𝗻𝗹𝘆, 𝗲𝗻𝗳𝗼𝗿𝗰𝗲𝗱 𝟯 𝘄𝗮𝘆𝘀:
     ▸ tools expose only read verbs (aks-mcp --access-level=readonly)
     ▸ the persona declines any write
     ▸ the output schema hard-fails on a change request

🗨️  "𝘚𝘤𝘢𝘭𝘦 𝘵𝘩𝘦 𝘮𝘰𝘥𝘦𝘭 / 𝘱𝘳𝘰𝘮𝘰𝘵𝘦 𝘢 𝘷𝘦𝘳𝘴𝘪𝘰𝘯."
      → politely refuses. Autonomy stops at the read layer. ✋

━━━━━━━━━━━━━━━━━━━━

𝗪𝗵𝘆 𝘁𝗵𝗮𝘁 𝗺𝗮𝘁𝘁𝗲𝗿𝘀

An AI agent you can trust in production is one that 𝗰𝗮𝗻'𝘁 touch it without you. Safety isn't a disclaimer — it's built into the architecture.

🛠️  𝗔𝗞𝗦 · 𝗔𝘇𝘂𝗿𝗲 𝗢𝗽𝗲𝗻𝗔𝗜 (gpt-4.1) · 𝗠𝗖𝗣 · 𝗞𝗔𝗜𝗧𝗢 · 𝗪𝗼𝗿𝗸𝗹𝗼𝗮𝗱 𝗜𝗱𝗲𝗻𝘁𝗶𝘁𝘆 · 𝗟𝗮𝗻𝗴𝗳𝘂𝘀𝗲 𝘁𝗿𝗮𝗰𝗶𝗻𝗴

Next: I let this same steward 𝗮𝗰𝘁 — but only through a human gate. That's iteration 2. 👇

#LLMOps #AIAgents #Kubernetes #AKS #Azure #MCP #MLOps #PlatformEngineering #KAITO
<<<

============================================================
POST #2B — INFERENCE STEWARD, ITERATION 2 (gated write + HITL)
============================================================
Media: attach a screen-capture showing the chat proposing → the GitHub PR it
opened → you merging → the steward reporting "executed". A 20–30s screen
recording of that full round-trip is the money shot. Fallback: a 3-panel
screenshot (proposal card / PR / "executed" reply).
>>>
𝗟𝗮𝘀𝘁 𝘄𝗲𝗲𝗸 𝗺𝘆 𝗔𝗜 𝘀𝘁𝗲𝘄𝗮𝗿𝗱 𝗰𝗼𝘂𝗹𝗱 𝗼𝗻𝗹𝘆 𝗹𝗼𝗼𝗸. 𝗡𝗼𝘄 𝗶𝘁 𝗰𝗮𝗻 𝗮𝗰𝘁 — 𝗯𝘂𝘁 𝗼𝗻𝗹𝘆 𝗶𝗳 𝗜 𝘀𝗮𝘆 𝘀𝗼. 🔐

Iteration 1 of the Inference Steward was 𝗿𝗲𝗮𝗱-𝗼𝗻𝗹𝘆 by design. The obvious next question: can an agent 𝗰𝗵𝗮𝗻𝗴𝗲 the cluster without becoming a liability?

My answer 👉 𝗦𝘁𝗲𝘄𝗮𝗿𝗱𝘀 𝗽𝗿𝗼𝗽𝗼𝘀𝗲. 𝗛𝘂𝗺𝗮𝗻𝘀 𝗱𝗶𝘀𝗽𝗼𝘀𝗲. — now with teeth.

━━━━━━━━━━━━━━━━━━━━

𝗧𝗵𝗲 𝗴𝗮𝘁𝗲𝗱-𝘄𝗿𝗶𝘁𝗲 𝗹𝗼𝗼𝗽 (𝗛𝗜𝗧𝗟)

1️⃣  You ask for a change.
2️⃣  The steward does a 𝗱𝗿𝘆-𝗿𝘂𝗻, then 𝗽𝗿𝗼𝗽𝗼𝘀𝗲𝘀 — it never claims it happened.
3️⃣  It opens a 𝗚𝗶𝘁𝗛𝘂𝗯 𝗣𝗥 with the exact preview + a proposal ID.
4️⃣  𝗠𝗲𝗿𝗴𝗲 = approve. 𝗖𝗹𝗼𝘀𝗲 = reject. Nothing else counts.
5️⃣  On merge, it executes 𝗼𝗻𝗰𝗲 and records an audit line.

The approver identity? Your 𝗿𝗲𝗮𝗹 𝗚𝗶𝘁𝗛𝘂𝗯 𝗹𝗼𝗴𝗶𝗻 from the merge. No fake "type YES to confirm."

━━━━━━━━━━━━━━━━━━━━

𝗜 𝘁𝗲𝘀𝘁𝗲𝗱 𝘁𝗵𝗲 𝟯 𝗼𝘂𝘁𝗰𝗼𝗺𝗲𝘀 𝘁𝗵𝗮𝘁 𝗺𝗮𝘁𝘁𝗲𝗿 — 𝗹𝗶𝘃𝗲 🧪

✅  𝗔𝗣𝗣𝗥𝗢𝗩𝗘 → "create a diagnostic pod"
      Proposed → PR opened → I merged → pod created. Audit: executed by my login.

🚫  𝗥𝗘𝗝𝗘𝗖𝗧 → I closed the PR
      Steward reports "no change made." The proposal can never be replayed.

🛑  𝗙𝗔𝗜𝗟-𝗖𝗟𝗢𝗦𝗘𝗗 → "scale the workspace to 2 replicas"
      The dry-run caught it: KAITO marks resource.count 𝗶𝗺𝗺𝘂𝘁𝗮𝗯𝗹𝗲. Denied at the gate — 𝗲𝘃𝗲𝗻 𝗶𝗳 𝗜 𝗮𝗽𝗽𝗿𝗼𝘃𝗲. The system refuses an operation the platform itself forbids.

That last one is my favourite. A safe agent isn't one that always succeeds — it's one that 𝗳𝗮𝗶𝗹𝘀 𝗵𝗼𝗻𝗲𝘀𝘁𝗹𝘆.

━━━━━━━━━━━━━━━━━━━━

𝗪𝗵𝘆 𝗮 𝗚𝗶𝘁𝗛𝘂𝗯 𝗣𝗥 𝗮𝘀 𝘁𝗵𝗲 𝗮𝗽𝗽𝗿𝗼𝘃𝗮𝗹 𝗰𝗵𝗮𝗻𝗻𝗲𝗹?

Because approval then requires 𝗿𝗲𝗽𝗼 𝘄𝗿𝗶𝘁𝗲 𝗮𝗰𝗰𝗲𝘀𝘀, every decision is 𝗿𝗲𝘃𝗶𝗲𝘄𝗮𝗯𝗹𝗲, and the merge leaves a permanent 𝗮𝘂𝗱𝗶𝘁 𝘁𝗿𝗮𝗶𝗹. Change management you already trust — reused for AI actuation.

Same steward. Same read safety. Now a 𝗴𝗮𝘁𝗲𝗱 𝗵𝗮𝗻𝗱 — with a human on it. 👇 Pipeline & Quality stewards got the same upgrade.

#LLMOps #AIAgents #Kubernetes #AKS #Azure #MCP #HumanInTheLoop #PlatformEngineering #KAITO
<<<

============================================================
POST #3 — STEWARD #2: THE PIPELINE STEWARD (+ how the two connect)
============================================================
>>>
𝗦𝘁𝗲𝘄𝗮𝗿𝗱 #𝟮 𝗶𝘀 𝗹𝗶𝘃𝗲: 𝘁𝗵𝗲 𝗣𝗶𝗽𝗲𝗹𝗶𝗻𝗲 𝗦𝘁𝗲𝘄𝗮𝗿𝗱. 🔗

And this is where MeshOps becomes a 𝗺𝗲𝘀𝗵.

━━━━━━━━━━━━━━━━━━━━

𝗪𝗵𝗮𝘁 𝗶𝘁 𝗱𝗼𝗲𝘀

The Pipeline Steward watches the 𝗠𝗟𝗢𝗽𝘀 side — the MLflow Model Registry.

📦  Which version is in Staging?
🚀  Which is in Production?
🗄️  Which got Archived?

Read-only, over the registry API — same 3-way no-write safety as steward #1.

━━━━━━━━━━━━━━━━━━━━

𝗛𝗲𝗿𝗲'𝘀 𝘁𝗵𝗲 𝗽𝗮𝗿𝘁 𝗜 𝗹𝗼𝘃𝗲 — 𝗵𝗼𝘄 𝘁𝗵𝗲 𝘁𝘄𝗼 𝗰𝗼𝗻𝗻𝗲𝗰𝘁

🔵  𝗣𝗶𝗽𝗲𝗹𝗶𝗻𝗲 (upstream) watches the registry → "version 2 is Production"
🟢  𝗜𝗻𝗳𝗲𝗿𝗲𝗻𝗰𝗲 (downstream) watches serving → "workspace healthy, 1 replica answering"

The registry's 𝗣𝗿𝗼𝗱𝘂𝗰𝘁𝗶𝗼𝗻 tag is the baton passed between them. 🏃‍♂️

I proved it live, side by side — asked both the same day:
▸ Pipeline: "Production = v2"
▸ Inference: "workspace healthy, serving"

Two independent agents. One coherent picture of the platform. 𝗧𝗵𝗮𝘁'𝘀 𝘁𝗵𝗲 𝗺𝗲𝘀𝗵.

━━━━━━━━━━━━━━━━━━━━

Four more stewards to go — 𝗤𝘂𝗮𝗹𝗶𝘁𝘆 · 𝗦𝗥𝗘 · 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 · 𝗦𝗲𝗰𝘂𝗿𝗶𝘁𝘆. Follow along. 👇

#LLMOps #MLOps #AIAgents #Kubernetes #AKS #Azure #MCP #PlatformEngineering
<<<
