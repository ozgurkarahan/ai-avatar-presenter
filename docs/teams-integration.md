# Teams Integration — Feasibility Analysis (V2)

## Executive Summary

Integrating the AI Presenter into Microsoft Teams meetings is **feasible** using Azure Communication Services (ACS) and the Bot Framework. The avatar bot would join a Teams meeting as a participant, stream its video feed, and speak slide content. This is significantly more complex than the web app and is recommended as a **V2 effort** after the web-based PoC is validated with the target organization.

---

## Architecture for Teams Integration

```
┌─────────────────────────────────────────────────────────┐
│                  Teams Meeting                          │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Human    │  │ AI Presenter │  │ Other            │  │
│  │ Users    │  │ Bot (avatar) │  │ Participants     │  │
│  └──────────┘  └──────┬───────┘  └──────────────────┘  │
└────────────────────────┼────────────────────────────────┘
                         │ ACS SDK / Real-Time Media
┌────────────────────────┼────────────────────────────────┐
│            AI Presenter Bot Service                     │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Azure Bot Service                                │   │
│  │ + Azure Communication Services                   │   │
│  │                                                  │   │
│  │  1. Join Teams meeting via ACS interop           │   │
│  │  2. Receive meeting events (slide changes, Q&A)  │   │
│  │  3. Generate avatar video (Azure AI Speech)      │   │
│  │  4. Stream video as bot's camera feed            │   │
│  │  5. Receive audio for Q&A (Azure Speech-to-Text) │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌────────────────┐  ┌────────────────┐                 │
│  │ AI Speech      │  │ Azure OpenAI   │                 │
│  │ (Avatar + TTS) │  │ (Q&A, Transl.) │                 │
│  └────────────────┘  └────────────────┘                 │
└─────────────────────────────────────────────────────────┘
```

---

## Integration Approaches

### Option A: ACS Interop (Recommended)

Azure Communication Services provides direct Teams meeting interoperability. The bot joins as an ACS user and can:
- Stream audio/video into the meeting
- Receive meeting audio for speech-to-text
- React to meeting events

**Pros:**
- Full programmatic control over audio/video streams
- Can inject avatar video as the bot's camera feed
- Well-documented APIs and SDKs (Python, JS, .NET)

**Cons:**
- Requires careful real-time media handling (encoding, frame rates)
- ACS user appears as "external" participant in Teams

### Option B: Teams Bot with Real-Time Media

Register a native Teams bot using the Bot Framework that uses the Real-Time Media Platform.

**Pros:**
- Bot appears as a native Teams participant
- Access to meeting context (who's presenting, slide info)

**Cons:**
- Real-Time Media Platform requires Windows VMs (for media processing)
- More complex setup and deployment
- Higher infrastructure costs

### Option C: Virtual Camera Approach

Run the avatar rendering locally and pipe it through a virtual camera (OBS, NDI) into a Teams meeting.

**Pros:**
- Simplest technically — no bot registration needed
- Works with any video conferencing tool, not just Teams

**Cons:**
- Not automated — requires manual setup per meeting
- Not scalable for production use

**Recommendation:** Start with **Option A (ACS Interop)** for the first Teams integration milestone.

---

## Required Azure Services (V2)

| Service | Purpose | Estimated Additional Cost |
|---------|---------|--------------------------|
| Azure Communication Services | Teams meeting interop | ~$0.004/min per participant |
| Azure Bot Service | Bot registration & management | Free (F0) for PoC |
| Azure Container Instances / AKS | Host bot service (always-on) | ~$30-100/month |
| Azure AI Speech (STT) | Transcribe meeting audio for Q&A | ~$1/hour of audio |

---

## Implementation Steps

1. **Register a Bot** in Azure Bot Service with Teams channel enabled
2. **Create ACS Resource** with Teams interop configured
3. **Build Bot Service** that:
   - Receives a Teams meeting join link
   - Joins via ACS with audio/video capabilities
   - Starts Azure AI Speech avatar rendering
   - Streams avatar video frames as the bot's outgoing video
4. **Add Presentation Controller** that:
   - Accepts slide navigation commands (next/prev/goto)
   - Triggers avatar speech for current slide notes
   - Handles translation on-the-fly
5. **Add Q&A Capability** that:
   - Transcribes participant speech (Azure STT)
   - Detects questions directed at the bot
   - Uses RAG pipeline to answer from slide content
   - Avatar speaks the answer
6. **Teams App Packaging** — Create Teams app manifest for sideloading or admin deployment

---

## Key Technical Challenges

| Challenge | Complexity | Notes |
|-----------|-----------|-------|
| Real-time video streaming into Teams | High | Encoding avatar frames to Teams-compatible video format |
| Audio processing & STT in meetings | Medium | Separating participant audio from bot's own audio |
| Slide navigation UX in Teams | Medium | How does the user control which slide the avatar presents? (chat commands, adaptive card) |
| Meeting orchestration | Medium | Handling join/leave, reconnection, multi-user scenarios |
| Teams admin consent | Low | Requires admin to approve the bot app |

---

## Effort Estimate

| Phase | Description | Effort |
|-------|-------------|--------|
| Bot scaffolding | Bot Framework + ACS setup | Medium |
| Media integration | Avatar video → ACS video stream | High |
| Slide control | Commands to navigate slides via chat | Low |
| Q&A in meetings | STT + RAG + avatar response | Medium |
| Testing & polish | End-to-end Teams meeting scenarios | Medium |
| **Total** | | **Significant** |

---

## Prerequisites

- Microsoft 365 tenant with Teams
- Azure subscription with ACS enabled
- Teams admin consent for bot sideloading
- V1 web app PoC completed (to reuse backend services)

---

## Conclusion

Teams integration is technically feasible using ACS interop. The web-based V1 PoC provides all the core services (PPT parsing, translation, avatar TTS, Q&A) that the Teams bot would reuse. The main additional work is the real-time media integration layer. Recommend completing V1 first, then pursuing Teams integration as a focused V2 sprint.
