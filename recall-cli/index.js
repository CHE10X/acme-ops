import { spawnSync } from "node:child_process";
import fs from "node:fs";

const RUNTIME_FILE = "/Users/AGENT/.openclaw/workspace/acme-ops/recall-cli/bin/recall_runtime.py";

function runRuntime(args) {
  if (!fs.existsSync(RUNTIME_FILE)) {
    console.error(`Recall runtime missing: ${RUNTIME_FILE}`);
    process.exitCode = 1;
    return;
  }

  const proc = spawnSync("python3", [RUNTIME_FILE, ...args], {
    encoding: "utf8",
    stdio: ["inherit", "pipe", "pipe"],
  });

  if (proc.stdout) {
    process.stdout.write(proc.stdout);
  }
  if (proc.stderr) {
    process.stderr.write(proc.stderr);
  }

  if (typeof proc.status === "number") {
    process.exitCode = proc.status;
  } else {
    process.exitCode = 1;
  }
}

export default function register(api) {
  api.registerCli(
    ({ program }) => {
      const recall = program
        .command("recall")
        .description("Manual intervention and recovery controls")
        .allowUnknownOption(true);

      recall
        .command("lockdown")
        .description("Enable global lock-down state")
        .action(() => {
          runRuntime(["lockdown"]);
        });

      recall
        .command("unlock")
        .description("Lift global lock-down state")
        .action(() => {
          runRuntime(["unlock"]);
        });

      recall
        .command("status")
        .description("Show fleet snapshot and recent interventions")
        .action(() => {
          runRuntime(["status"]);
        });

      recall
        .command("log [agent]")
        .description("Show recall intervention history")
        .action((agent) => {
          const args = ["log"];
          if (agent) {
            args.push(agent);
          }
          runRuntime(args);
        });

      recall
        .command("freeze <agent>")
        .description("Prevent sub-agent spawning for agent")
        .action((agent) => {
          runRuntime(["freeze", String(agent)]);
        });

      recall
        .command("unfreeze <agent>")
        .description("Restore sub-agent spawning for agent")
        .action((agent) => {
          runRuntime(["unfreeze", String(agent)]);
        });

      recall
        .command("stall")
        .description("Pause an agent (or all known agents)")
        .allowUnknownOption(true)
        .option("--all", "Apply to all discovered agents")
        .argument("[agent]")
        .action((agent, options) => {
          const argv = process.argv;
          const explicitAll = options.all || argv.includes("--all");
          const hasAgent = Boolean(agent);

          if (!explicitAll && !hasAgent) {
            console.error("Usage: openclaw recall stall <agent> | --all");
            process.exitCode = 1;
            return;
          }

          const args = ["stall"];
          if (explicitAll) {
            args.push("--all");
          } else if (agent) {
            args.push(String(agent));
          }
          runRuntime(args);
        });

      recall
        .command("sleep")
        .description("Disconnect agent from channel(s)")
        .allowUnknownOption(true)
        .option("--all", "Apply to all known agents")
        .option("--channel <channel>", "Disconnect only this channel")
        .argument("[agent]")
        .action((agent, options) => {
          const argv = process.argv;
          const explicitAll = options.all || argv.includes("--all");
          const channel = options.channel;

          if (!explicitAll && !agent) {
            console.error("Usage: openclaw recall sleep <agent> [--channel <id>] | --all");
            process.exitCode = 1;
            return;
          }

          const args = ["sleep"];
          if (explicitAll) {
            args.push("--all");
          } else {
            args.push(String(agent));
          }
          if (channel) {
            args.push("--channel", String(channel));
          }
          runRuntime(args);
        });

      recall
        .command("stun <agent>")
        .description("Full intervention: disconnect + drain + kill sub-agents + archive + compact")
        .allowUnknownOption(true)
        .option("--capture-bundle", "Capture support bundle before stun")
        .action((agent, options) => {
          const argv = process.argv;
          const capture = options.captureBundle || argv.includes("--capture-bundle");
          const args = ["stun", String(agent)];
          if (capture) {
            args.push("--capture-bundle");
          }
          runRuntime(args);
        });

      recall
        .command("quarantine <agent>")
        .description("Isolate stunned agent for inspection")
        .action((agent) => {
          runRuntime(["quarantine", String(agent)]);
        });

      recall
        .command("wake")
        .description("Reverse stall/sleep and allow post-recover stunned agents to reconnect")
        .allowUnknownOption(true)
        .option("--all", "Wake all known agents")
        .option("--channel <channel>", "Wake only this sleep channel")
        .argument("[agent]")
        .action((agent, options) => {
          const argv = process.argv;
          const explicitAll = options.all || argv.includes("--all");
          const channel = options.channel;

          if (!explicitAll && !agent) {
            console.error("Usage: openclaw recall wake <agent> | --all");
            process.exitCode = 1;
            return;
          }

          const args = ["wake"];
          if (explicitAll) {
            args.push("--all");
          } else {
            args.push(String(agent));
          }
          if (channel) {
            args.push("--channel", String(channel));
          }
          runRuntime(args);
        });

      recall
        .command("recover <agent>")
        .description("Post-stun recovery assistant")
        .action((agent) => {
          runRuntime(["recover", String(agent)]);
        });

      recall
        .command("focus <agent>")
        .description("Pause all other agents; keep named agent active")
        .action((agent) => {
          runRuntime(["focus", String(agent)]);
        });

      recall
        .command("unfocus")
        .description("Release focus and restore prior stall states")
        .action(() => {
          runRuntime(["unfocus"]);
        });

      recall
        .command("reset")
        .description("Safe infrastructure restart + verification")
        .option("--no-interactive", "Skip confirmation prompts")
        .action((options) => {
          const argv = process.argv;
          const noInteractive = options.noInteractive || argv.includes("--no-interactive");
          if (noInteractive) {
            runRuntime(["reset", "--no-interactive"]);
          } else {
            runRuntime(["reset"]);
          }
        });

      recall
        .addHelpText(
          "after",
          "\nCommands: lockdown unlock status log freeze unfreeze stall sleep stun quarantine wake recover focus unfocus reset",
        );
    },
    { commands: ["recall"] },
  );
}
