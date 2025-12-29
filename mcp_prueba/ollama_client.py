import os
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings
from llama_index.core.agent.workflow import (
    FunctionAgent,
    ToolCallResult,
    ToolCall,
                                             )
from llama_index.core.workflow import Context

SYSTEM_PROMPT = """
Usa herramientas cuando sea necesario.
Si la información ya está en el contexto de la conversación, puedes responder sin usar tools.
Si no sabes la respuesta, responde con "No sé".
"""


app = FastAPI()

_agent: Optional[FunctionAgent] = None
_agent_ctx: Optional[Context] = None


class MessageRequest(BaseModel):
    message: str


async def write_tools(tools): 
    for tool in tools:
        print(tool.metadata.name, tool.metadata.description)
        
def get_agent(tools, llm: Ollama):
    agent = FunctionAgent(
        name="Jorge",
        description="Un asistente que puede responder",
        tools=tools,
        llm=llm,
        system_prompt=SYSTEM_PROMPT
    )
    return agent


async def handle_user_message(
        message_content: str,
        agent : FunctionAgent,
        agent_context : Context,
        verbose : bool = False
):
    handler = agent.run(message_content, ctx = agent_context)
    async for event in handler.stream_events():
        if verbose and type(event) == ToolCall:
            print(f" -- Llamando a la tool '{event.tool_name}' con los argumentos '{event.tool_kwargs}' --")
        elif verbose and type(event) == ToolCallResult:
            print(f"Tool {event.tool_name} respondio con {event}")
    response = await handler
    return str(response)


async def gather_tools_from_urls(urls, retry_seconds=2, max_retries=30):
    mcp_tools = []
    for url in urls:
        #Inicializa el cliente MCP y crea el agente.
        client = BasicMCPClient(url)
        spec = McpToolSpec(client=client)

        retries = 0
        while True:
            try:
                tools = await spec.to_tool_list_async()
                print(f"[ok] Conectado a {url}, tools: {len(tools)}")
                mcp_tools.extend(tools)
                break
            except Exception as e:
                retries += 1
                print(f"[warn] No se pudo conectar a {url}: {e} (intento {retries})")
                if retries >= max_retries:
                    print(f"[error] Max retries alcanzado para {url}, lo omito.")
                    break
                await asyncio.sleep(retry_seconds)
    return mcp_tools


@app.on_event("startup")
async def startup_event():
    global _agent, _agent_ctx

    #Setup llm Ollama
    llm = Ollama(model= "qwen3:32b",
                 base_url="http://192.168.30.50:31416"
                 ,requests_timeout=300)
    Settings.llm = llm

    #Setup tools
    mcp_urls_env = os.environ.get("MCP_SERVERS")
    if not mcp_urls_env:
        print("[warn] No se encontró MCP_SERVERS en variables de entorno. No se cargarán tools.")
        mcp_urls = []
    else:
        mcp_urls = [u.strip() for u in mcp_urls_env.split(",") if u.strip()]
            
    mcp_tools = await gather_tools_from_urls(mcp_urls)
    if not mcp_tools:
        print("[error] No se obtuvieron tools desde ningun MCP. Revisar servidores.")
    else:
        await write_tools(mcp_tools)

    #Setup Agent
    _agent = get_agent(mcp_tools, llm)
    _agent_ctx = Context(_agent)
    print("[info] Agent inicializado. Endpoint /api/agent listo.")


@app.post("/api/agent")
async def api_agent(req: MessageRequest):
    global _agent, _agent_ctx
    if _agent is None or _agent_ctx is None:
        raise HTTPException(status_code=500, detail="Agent no inicializado aún o no hay tools cargadas.")

    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="El campo 'message' no puede estar vacío.")

    try:
        response = await handle_user_message(user_input, _agent, _agent_ctx, verbose=True)
        return {"response": response}
    except Exception as e:
        print("[error] Al procesar la petición:", e)
        raise HTTPException(status_code=500, detail=str(e))
