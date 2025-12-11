from praisonaiagents import Agent, MCP

inst="""Tu trabajo es responder de la mejor forma posible. Solamente usa las tools (herramientas) a tu disposicion en caso de ser completamente necesario"""

agent = Agent (
    instructions=inst,
    llm="ollama/gemma3:12b",
    tools=MCP("npx -y @modelcontextprotocol/server-filesystem C:/Users/NICOLAS/Desktop/2025/Trabajo/test_mcp/data")
)

#agent = Agent (
#    instructions=inst,
#    llm="ollama/llama3.2:latest",
#    tools=MCP("npx -y @modelcontextprotocol/server-filesystem C:/Users/NICOLAS/Desktop/2025/Trabajo/test_mcp/data")
#)

if __name__ == "__main__":
    query = input("Consulta: ").strip()
    while(query.lower()!="exit"):
        result = agent.start(query)
        print (f"## Resultados de la busqueda: \n\n{result}")
        query = input("Consulta: ").strip()