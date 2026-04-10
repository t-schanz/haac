# haac — Home Assistant as Code

Terraform-style configuration management for Home Assistant. Define your entire HA setup in YAML, diff it, deploy it.

## Why haac exists

I wanted to vibe code my home automations. The dream:

> "Hey Claude, add an automation that notifies me when my washing machine finishes."

And have it actually work — an AI assistant that understands my home setup, writes the automation YAML, and deploys it. No clicking through UIs, no copy-pasting config.

But that wasn't possible with existing tools. Home Assistant splits its config across YAML files on the instance, UI-only settings in `.storage/`, and various registries that can only be changed through the web interface. An AI coding assistant can edit YAML in a git repo, but it can't click buttons in a browser.

So on the way, a bit unplanned, **haac** was born — a tool that manages *everything* through code. Floors, areas, device assignments, entity names, automations, scenes, dashboards — all defined in YAML, all deployed via API. No YAML on the HA instance. No git deploy. No cron. Just:

```bash
haac plan    # see what would change
haac apply   # make it so
```

Now the dream works. An AI assistant (or a human with a text editor) can manage an entire Home Assistant setup from a git repo.

## Install

```bash
pip install haac
```

## Quick Start

```bash
mkdir my-ha && cd my-ha
git init
haac init     # connect to your HA instance
haac pull     # import your current setup
git add -A && git commit -m "initial import"
```

That's it. Your entire HA config is now in version-controlled YAML files.

## Usage

```bash
haac plan          # show what would change in HA
haac apply         # push changes to HA
haac pull          # pull new HA state into local files (additive only)
haac fetch         # refresh entity inventory snapshots
haac delete kind:id  # remove specific resources from HA
```

### Workflow

```
Edit state/*.yaml → haac plan → review → haac apply
```

Make a change, see what it does, deploy it. Like terraform, but for your home.

### Pulling from HA

Changed something in the UI? Pull it back:

```bash
haac pull          # adds new items, never removes existing ones
git diff           # review what changed
git commit         # save it
```

## What haac manages

| State file | What it controls |
|---|---|
| `state/floors.yaml` | Floors (Erdgeschoss, Obergeschoss, ...) |
| `state/areas.yaml` | Areas/rooms with floor assignments |
| `state/labels.yaml` | Labels with colors and icons |
| `state/assignments.yaml` | Device-to-area mappings (glob patterns) |
| `state/entities.yaml` | Entity names and icons |
| `state/automations.yaml` | Automations (triggers, conditions, actions) |
| `state/scenes.yaml` | Scenes (light states, switch states) |
| `state/helpers.yaml` | Input helpers (input_boolean, etc.) |
| `state/dashboard.yaml` | Lovelace dashboard |

Each file is optional. Only manage what you want — adopt incrementally.

## How it works

haac talks to Home Assistant via the WebSocket and REST APIs. It reads your local YAML files (desired state), fetches the current HA state, diffs them, and applies the changes. Resources are matched by name, not by internal IDs — so your YAML stays human-readable.

```
state/*.yaml  →  haac plan/apply  →  HA WebSocket/REST API
     ↑                                       |
     └──────────  haac pull  ──────────────────┘
```

### Safety

- `haac plan` is read-only — it never changes anything
- `haac apply` only creates and updates — it never deletes
- `haac pull` is additive — it adds new items, never removes existing ones
- Unmanaged resources (in HA but not in your files) are reported, not touched
- Use `haac delete kind:id` for explicit, intentional removal

## Project structure

After `haac init` and `haac pull`:

```
my-ha/
  haac.yaml          # connection config (HA URL)
  .env               # HA_TOKEN (gitignored)
  state/             # your desired HA state
    floors.yaml
    areas.yaml
    labels.yaml
    assignments.yaml
    entities.yaml
    automations.yaml
    scenes.yaml
    helpers.yaml
    dashboard.yaml
  entities/          # read-only inventory (haac fetch)
    lights.yaml
    switches.yaml
    ...
```

## Configuration

### haac.yaml

```yaml
ha_url: "http://homeassistant.local:8123"
```

### .env

```
HA_TOKEN=your-long-lived-access-token
```

Generate a token at: `http://your-ha:8123/profile` → Long-Lived Access Tokens.

## Requirements

- Python 3.12+
- Home Assistant 2024.1+ (WebSocket API v2)
- A long-lived access token

## The vibe coding dream

With haac, your HA config is just YAML files in a git repo. That means any AI coding assistant can:

1. Read your current setup (`state/*.yaml`)
2. Understand your home (rooms, devices, automations)
3. Write new automations, scenes, or config changes
4. Preview with `haac plan`
5. Deploy with `haac apply`

No browser automation. No screenshots. No "now click this button." Just code.

## License

MIT
