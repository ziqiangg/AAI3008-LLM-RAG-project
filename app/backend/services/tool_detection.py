"""
Never ask Gemini to write Mermaid syntax directly.
Instead, ask for JSON (nodes + edges), then build the Mermaid ourselves.
This avoids all Gemini syntax hallucinations entirely.
"""
import logging
import re
import json
import google.generativeai as genai
from app.backend.config import Config

logger = logging.getLogger(__name__)

# ─── Step 1: Detect which tool is needed ────────────────────────────────────

DETECTION_PROMPT = """You are a tool-routing assistant.

Reply with ONLY one word — nothing else.

Reply MERMAID if the question asks for any diagram, chart, flowchart, use case diagram,
activity diagram, sequence diagram, or any visual representation.

Reply DESMOS if the question contains any of these:
- plot, graph, draw a function, visualize equation, show equation
- any mathematical function like y=, f(x)=, sin, cos, tan, quadratic, linear
- "what does X look like", "graph of X"

Reply NONE only if it is purely a text/explanation question.

Question: {question}

Reply with exactly one word: MERMAID, DESMOS, or NONE"""


# ─── Step 2a: Extract diagram data as JSON (NOT Mermaid syntax) ─────────────

MERMAID_DATA_PROMPT = """Extract the diagram structure from the question and context.
Return ONLY a valid JSON object. No markdown fences, no explanation, no extra text.

Use this exact structure:
{{
  "nodes": [
    {{"id": "n1", "label": "Label Text", "shape": "round"}},
    {{"id": "n2", "label": "Label Text", "shape": "box"}}
  ],
  "edges": [
    {{"from": "n1", "to": "n2", "label": ""}},
    {{"from": "n1", "to": "n3", "label": "includes"}}
  ]
}}

Shape rules:
- "round"   → use cases, activities, processes  (renders as oval/rounded)
- "box"     → actors, systems, start/end states (renders as rectangle)
- "diamond" → decisions                          (renders as diamond)

Strict limits: max 10 nodes, max 12 edges.
Node IDs must be simple alphanumeric strings like n1, n2, uc1, act1 — NO spaces, NO colons, NO special chars.
Edge labels should be short: "includes", "extends", "yes", "no", or empty string "".

Question: {question}
Context: {context}"""


# ─── Step 2b: Extract Desmos expressions ────────────────────────────────────

DESMOS_PROMPT = """Extract mathematical expressions to plot on a Desmos graph.
Return ONLY a valid JSON array of LaTeX expression strings.
No markdown fences, no explanation.

Example output: ["y=x^2", "y=2x+1", "y=\\\\sin(x)"]

Keep it to 1-5 expressions maximum.

Question: {question}
Context: {context}"""


# ─── Mermaid builder ─────────────────────────────────────────────────────────

def build_mermaid_from_data(data: dict) -> str:
    """
    Build guaranteed-valid Mermaid graph TD code from structured JSON.
    We construct the syntax ourselves — Gemini never touches Mermaid directly.
    """
    lines = ["graph TD"]

    shape_open  = {"round": "(", "box": "[", "diamond": "{"}
    shape_close = {"round": ")", "box": "]", "diamond": "}"}

    for node in data.get("nodes", []):
        # Sanitize node ID: only alphanumeric + underscore
        nid   = re.sub(r'[^a-zA-Z0-9_]', '_', str(node.get("id", "n0")))
        label = str(node.get("label", "Node")).replace('"', "'")
        shape = node.get("shape", "round")
        o = shape_open.get(shape, "(")
        c = shape_close.get(shape, ")")
        lines.append(f'    {nid}{o}"{label}"{c}')

    for edge in data.get("edges", []):
        src   = re.sub(r'[^a-zA-Z0-9_]', '_', str(edge.get("from", "")))
        dst   = re.sub(r'[^a-zA-Z0-9_]', '_', str(edge.get("to", "")))
        label = str(edge.get("label", "")).strip()
        if not src or not dst:
            continue
        if label:
            safe_label = label.replace('"', "'")
            lines.append(f'    {src} -->|"{safe_label}"| {dst}')
        else:
            lines.append(f'    {src} --> {dst}')

    return "\n".join(lines)


# ─── Gemini caller ───────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> str:
    genai.configure(api_key=Config.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=Config.LLM_MODEL,
        generation_config={"temperature": 0.1, "max_output_tokens": 2048}
    )
    response = model.generate_content(prompt)
    # Log why generation stopped
    try:
        finish = response.candidates[0].finish_reason
        logger.warning(f"[ToolDetection] Gemini finish_reason: {finish}")
    except Exception:
        pass
    try:
        return "".join(part.text for part in response.parts).strip()
    except Exception:
        return response.text.strip()


def _parse_json_response(raw: str):
    """Strip markdown fences and parse JSON safely."""
    # Remove all ``` fences with or without language tag
    raw = re.sub(r'```[a-zA-Z]*', '', raw)
    raw = raw.replace('`', '').strip()
    
    # Find the JSON object/array within the text
    # Look for first { or [ and last } or ]
    start = min(
        (raw.find('{') if '{' in raw else len(raw)),
        (raw.find('[') if '[' in raw else len(raw))
    )
    end = max(raw.rfind('}'), raw.rfind(']')) + 1
    
    if start < end:
        raw = raw[start:end]
    
    return json.loads(raw)


# ─── Main entry point ────────────────────────────────────────────────────────

def detect_and_generate_tool(question: str, context_chunks: list, forced_type: str = None):
    """
    Detect if a visual tool is needed and generate its data.

    Returns one of:
        {"type": "mermaid", "code": "graph TD\\n  ..."}
        {"type": "desmos",  "expressions": ["y=x^2", ...]}
        None  (if no tool needed)
    """
    try:
        # Summarise context for detection prompt (keep short)
        full_context = "\n".join(
            c.get("content", "") for c in context_chunks[:5]
        )

        # ── Step 1: Classify ──────────────────────────────────────────────
        if forced_type:
            decision = forced_type.upper().strip()
        else:
            raw_decision = _call_gemini(
                DETECTION_PROMPT.format(
                    question=question,
                    context=full_context,
                )
            ).upper().strip()
            decision = raw_decision.split()[0] if raw_decision else "NONE"

        logger.info(f"[ToolDetection] Decision: {decision}")

        # ── Step 2a: Build Mermaid from JSON data ─────────────────────────
        if decision == "MERMAID":
            raw = _call_gemini(
                MERMAID_DATA_PROMPT.format(
                    question=question,
                    context=full_context
                )
            )
            try:
                diagram_data = _parse_json_response(raw)
                code = build_mermaid_from_data(diagram_data)
                logger.info(f"[ToolDetection] Mermaid built: {len(diagram_data.get('nodes', []))} nodes, {len(diagram_data.get('edges', []))} edges")
                return {"type": "mermaid", "code": code}
            except Exception as e:
                logger.warning(f"[ToolDetection] Mermaid JSON parse failed: {e} | raw={raw[:1000]}")
                return None

        # # ── Step 2b: Desmos expressions ───────────────────────────────────
        if decision == "DESMOS":
            raw = _call_gemini(
                DESMOS_PROMPT.format(
                    question=question,
                    context=full_context
                )
            )
            try:
                expressions = _parse_json_response(raw)
                if isinstance(expressions, list) and len(expressions) > 0:
                    logger.info(f"[ToolDetection] Desmos: {len(expressions)} expressions")
                    return {"type": "desmos", "expressions": expressions}
            except Exception as e:
                logger.warning(f"[ToolDetection] Desmos JSON parse failed: {e} | raw={raw[:300]}")
                return None

    except Exception as e:
        logger.warning(f"[ToolDetection] Tool detection failed entirely: {e}")

    return None