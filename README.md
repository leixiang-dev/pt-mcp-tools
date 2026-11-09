# PT Home Exercise Tools: MCP Server

An MCP server with five analytical tools for home physical therapy exercise, built for a CMU course project on digital home PT for older adults.

| Tool | What it does |
| --- | --- |
| `joint_angle` | Angle at a joint from three 2D points, checked against a PT target range |
| `session_time` | Session length, share of time moving, and whether it fits a time budget |
| `rom_projection` | Days to a range-of-motion target at the current rate |
| `set_check` (new) | After one set: reps in range, pain zone, and the next step (continue, adjust form, or stop and ask the PT) |
| `weekly_summary` (new) | Weekly summary for the PT: sessions vs prescribed, longest gap, pain flags, patient questions |

These tools do arithmetic on the numbers they are given. They do not diagnose. Target ranges and the pain limit are settings the patient's PT owns.

## Setup

Requires Python 3.10 or newer and Node.js 18 or newer (Node is only needed for MCP Inspector).

```bash
git clone <this repo's URL>
cd pt-mcp-tools
pip install "mcp>=2"
```

## Run

```bash
python pt_tools_server.py
```

The server uses the stdio transport, so it waits silently for an MCP client. Stop it with Ctrl+C.

## Test with MCP Inspector

Browser interface:

```bash
npx @modelcontextprotocol/inspector python pt_tools_server.py
```

Command line, for example:

```bash
npx @modelcontextprotocol/inspector --cli python pt_tools_server.py --method tools/list
npx @modelcontextprotocol/inspector --cli python pt_tools_server.py --method tools/call \
  --tool-name joint_angle --tool-arg ax=300 ay=250 bx=360 by=400 cx=310 cy=560 target_min_deg=80 target_max_deg=100
```

`recorded_calls.md` has the recorded calls and raw responses, including two invalid-input cases.

## Use with Claude Desktop (optional)

Add this to `claude_desktop_config.json`, using the full path to the file:

```json
{
  "mcpServers": {
    "pt-home-exercise-tools": {
      "command": "python",
      "args": ["/full/path/to/pt_tools_server.py"]
    }
  }
}
```

## Invalid input

Out-of-range or contradictory inputs return an MCP result with `isError: true` and a plain message, never a number. Ranges are published in each tool's input schema.
