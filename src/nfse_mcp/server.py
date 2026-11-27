"""MCP Server for NFS-e emission (Brasilia/DF - ISS.net ABRASF 2.04 + SEFIN Nacional).

Thin transport adapter: creates the FastMCP app and registers tools.
All business logic lives in Application Services; all tool definitions live in
presentation/mcp/tools.py; all dependency injection lives in presentation/mcp/container.py.
"""

from mcp.server.fastmcp import FastMCP
from nfse_mcp.presentation.mcp.tools import register_tools


mcp = FastMCP("nfse")
register_tools(mcp)


def main():
    """Run the NFS-e MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
