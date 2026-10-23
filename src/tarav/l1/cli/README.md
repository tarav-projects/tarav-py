# Global command routing

The CLI optionally reads `$TARAV_HOME/cli-routes.json` (default
`~/.tarav/cli-routes.json`). Reads do not create this file. There are no
Project-local routes. An absent file or an empty `routes` array retains ordinary
CLI behavior.

A route matches a leading array of command tokens, excluding the initial
`tarav`. The longest matching path wins; duplicate paths are errors. Put the
command tokens before its options. Remaining arguments are passed unchanged
to the target, without local argument validation, so a route can name a command
installed only on another machine.

For example, this file routes a hypothetical future Chatlas vector command:
<!-- tarav.breadcrumb 0b46ccd539e0 -->

```json
{
  "routes": [
    {
      "command": ["chatlas", "vector"],
      "argv": ["ssh", "studio-pereiro"],
      "shell_command": ["env", "TARAV_CLI_NO_ROUTE=1", "tarav", "chatlas", "vector"]
    }
  ]
}
```

`argv` is the external executable and its fixed arguments. Without
`shell_command`, forwarded arguments are appended directly to it. With
`shell_command`, that token array and the forwarded arguments become one
POSIX-shell-quoted string appended to `argv`. This is needed because SSH sends
its remote command through a shell. Spaces, empty arguments, quotes and shell
metacharacters retain their literal values. The router itself starts no shell
and performs no template or environment-variable expansion.

Every routed invocation prints `Routed to: <shell-quoted actual invocation>` to
stderr before starting the child, including the SSH invocation. The child
inherits stdin, stdout, stderr and local cwd; the router returns its exit status
(128 plus signal number for a signaled child). SSH determines the remote cwd;
local paths, files and environments are not copied automatically.
<!-- tarav.breadcrumb 6aa6d3adff89 -->

`TARAV_CLI_NO_ROUTE=1 tarav …` bypasses routing, including invalid configuration.
Routed local children inherit that setting to prevent re-routing loops. SSH does
not forward it automatically: the example sets it on the remote side explicitly.
Remove a route or use this bypass to restore local execution. Unknown fields,
malformed JSON and invalid route values report an error without running a target.

This example configures no live route and does not create a vector database,
install remote Tarav, or introduce run profiles or an SSH subsystem.
