# Foundry agent connection

## Official project and Pinokio community

The original project, maintained by **mumblebox-gpt**, is [Mumblebox Foundry on GitHub](https://github.com/mumblebox-gpt/mumblebox-foundry). Follow that repository for ongoing development and use its [published releases](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) for release notes and available downloads. If you are reading a fork or a copied README, follow these links back to the original project; a fork may have different changes or an older version.

We are proud to build alongside the [Pinokio](https://pinokio.co/) creator community. Pinokio makes local tools easier to install and share, and we value a community where creators can discover each other's projects, exchange useful feedback and learn together. Thank you to cocktail peanut and everyone contributing to that creative ecosystem. [Find Foundry on Pinokio](https://pinokio.co/apps/github-com-mumblebox-gpt-mumblebox-foundry).

Use `foundry_server.py` for the current Mumblebox 3D Asset Foundry image creator, Gallery, 3D wizard and independent HairDeck wizard. Its tools share the application's workflow services, including paired generation, selected-area editing, accepted-image handoff and saved hair generations/exports. Setup, tool descriptions and example client configuration are in the release's `docs/AGENT-SETUP.md`.

`mcp_server.py` and its companion client are retained for older image-project integrations. They are not the entry point for the current five-page Foundry workflow. Both adapters use local HTTP services and their own lightweight environment; neither should install its MCP dependencies into ComfyUI's inference Python.
