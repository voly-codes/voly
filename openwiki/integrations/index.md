# Files

- [Model gateway and Cloudflare integration boundaries](gateway-and-cloudflare.md) - AIGateway.chat() is the protected model-call boundary for Python callers, while Cloudflare Workers provide separately versioned HTTP and JSON contracts for inference, federation, spend, and telemetry.
- [Programmable SDK and MCP surfaces](sdk-and-mcp.md) - VOLY exposes a Python Agent and Workflow SDK that compiles into the governed Plan runtime, plus an MCP server that exposes the existing web-service run and telemetry operations to MCP hosts.
