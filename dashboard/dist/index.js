/**
 * Kanban-Advanced Dashboard Plugin
 *
 * Settings page for the kanban-advanced multi-agent governance workflow.
 * No build step — plain IIFE using window.__HERMES_PLUGIN_SDK__ globals.
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) { console.error("[kanban-advanced] Plugin SDK not found"); return; }

  var React = SDK.React;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var Card = SDK.components.Card;
  var CardHeader = SDK.components.CardHeader;
  var CardTitle = SDK.components.CardTitle;
  var CardContent = SDK.components.CardContent;
  var Badge = SDK.components.Badge;
  var Button = SDK.components.Button;
  var Input = SDK.components.Input;
  var Label = SDK.components.Label;
  var Select = SDK.components.Select;
  var SelectTrigger = SDK.components.SelectTrigger || "select";
  var SelectContent = SDK.components.SelectContent || "div";
  var SelectItem = SDK.components.SelectItem || "option";
  var SelectValue = SDK.components.SelectValue || "span";
  var Separator = SDK.components.Separator;
  var cn = SDK.utils.cn;
  var fetchJSON = SDK.api.fetchJSON || SDK.fetchJSON;

  // ── API helpers ──
  function apiStatus() { return fetchJSON("/api/plugins/kanban-advanced/status"); }
  function apiInit(data) { return fetchJSON("/api/plugins/kanban-advanced/init", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }); }
  function apiUpdate(data) { return fetchJSON("/api/plugins/kanban-advanced/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }); }

  var CODING_AGENTS = [
    { value: "agent", label: "agent (Cursor CLI)" },
    { value: "claude", label: "claude (Claude Code)" },
    { value: "codex", label: "codex (OpenAI Codex)" },
    { value: "grok", label: "grok (grok-cli)" },
    { value: "aider", label: "aider (Aider)" },
    { value: "gemini", label: "gemini (Gemini CLI)" },
    { value: "__custom__", label: "Other (custom binary)…" }
  ];

  // ── Status dot ──
  function StatusDot(props) {
    var color = props.status === "ok" ? "bg-green-500"
      : props.status === "warn" ? "bg-yellow-500"
      : "bg-muted-foreground/30";
    return React.createElement("span", { className: cn("inline-block w-2 h-2 rounded-full flex-shrink-0", color) });
  }

  // ── Main page ──
  function KanbanAdvancedPage() {
    var _useState = useState(null), status = _useState[0], setStatus = _useState[1];
    var _useState2 = useState(false), loading = _useState2[0], setLoading = _useState2[1];
    var _useState3 = useState("main"), workingBranch = _useState3[0], setWorkingBranch = _useState3[1];
    var _useState4 = useState("agent"), codingAgent = _useState4[0], setCodingAgent = _useState4[1];
    var _useState5 = useState(""), customAgent = _useState5[0], setCustomAgent = _useState5[1];
    var _useState6 = useState(180), maxTurns = _useState6[0], setMaxTurns = _useState6[1];
    var _useState7 = useState([]), consoleLines = _useState7[0], setConsoleLines = _useState7[1];
    var _useState8 = useState(false), bootstrapping = _useState8[0], setBootstrapping = _useState8[1];
    var _useState9 = useState(false), initialized = _useState9[0], setInitialized = _useState9[1];

    function loadStatus() {
      apiStatus().then(function (s) {
        setStatus(s);
        if (s.config_exists) setInitialized(true);
        if (s.working_branch) setWorkingBranch(s.working_branch);
        if (s.coding_agent) {
          var found = CODING_AGENTS.some(function (a) { return a.value === s.coding_agent; });
          if (found) setCodingAgent(s.coding_agent);
          else { setCodingAgent("__custom__"); setCustomAgent(s.coding_agent); }
        }
        if (s.max_turns) setMaxTurns(s.max_turns);
      }).catch(function () {
        setStatus({ error: "API unreachable" });
      });
    }

    useEffect(function () { loadStatus(); }, []);

    function getFormData() {
      var agent = codingAgent === "__custom__" ? (customAgent.trim() || "agent") : codingAgent;
      return {
        working_branch: workingBranch.trim() || "main",
        coding_agent_binary: agent,
        max_turns: parseInt(maxTurns) || 180
      };
    }

    function addLines(lines, cls) {
      setConsoleLines(function (prev) {
        var next = prev.slice();
        lines.forEach(function (l) {
          var lineCls = l.indexOf("   X") === 0 || l.indexOf("Error") === 0 ? "line-err"
            : l.indexOf("   !") === 0 ? "line-warn"
            : l.indexOf("   OK") === 0 ? "line-ok"
            : "";
          next.push({ text: l, cls: lineCls || cls || "" });
        });
        return next;
      });
    }

    function runBootstrap() {
      setBootstrapping(true);
      setConsoleLines([]);
      var data = getFormData();
      addLines(["=== Bootstrap starting ===", "Working branch: " + data.working_branch, "Coding agent: " + data.coding_agent_binary, "Max turns: " + data.max_turns, ""]);
      apiInit(data).then(function (r) {
        if (r.error) {
          addLines(["ERROR: " + r.error], "line-err");
        } else if (r.output) {
          addLines(r.output);
          if (r.success) setInitialized(true);
        }
        setBootstrapping(false);
        loadStatus();
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setBootstrapping(false);
      });
    }

    function runUpdate() {
      setBootstrapping(true);
      setConsoleLines([]);
      var data = getFormData();
      addLines(["=== Updating settings ===", "Working branch: " + data.working_branch, "Coding agent: " + data.coding_agent_binary, "Max turns: " + data.max_turns, ""]);
      apiUpdate(data).then(function (r) {
        if (r.output) addLines(r.output);
        setBootstrapping(false);
        loadStatus();
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setBootstrapping(false);
      });
    }

    // ── Render helpers ──
    function profileBadge(info) {
      if (!info || !info.exists) return React.createElement(Badge, { variant: "outline", className: "text-muted-foreground" }, "not found");
      if (!info.has_model) return React.createElement(Badge, { variant: "outline", className: "text-yellow-500 border-yellow-500/30" }, "exists (no model)");
      return React.createElement(Badge, { variant: "outline", className: "text-green-500 border-green-500/30" }, "configured (" + (info.model || "?") + ")");
    }

    function gatewayBadge(gw) {
      if (!gw) return React.createElement(Badge, { variant: "outline", className: "text-muted-foreground" }, "unknown");
      if (gw.running) return React.createElement(Badge, { variant: "outline", className: "text-green-500 border-green-500/30" }, "running");
      return React.createElement(Badge, { variant: "outline", className: "text-yellow-500 border-yellow-500/30" }, "not running");
    }

    var statusInitialized = status && status.config_exists;
    var statusError = status && status.error;

    return React.createElement("div", { className: "space-y-6 max-w-2xl" },

      // ── Status banner ──
      React.createElement(Card, { className: statusError ? "border-red-500/30" : statusInitialized ? "border-green-500/30" : "" },
        React.createElement(CardContent, { className: "flex items-center gap-3 py-4" },
          React.createElement(StatusDot, { status: statusError ? "error" : statusInitialized ? "ok" : "warn" }),
          React.createElement("div", { className: "flex-1" },
            React.createElement("p", { className: "text-sm font-medium" },
              statusError ? "Cannot reach API"
                : statusInitialized ? "Initialized"
                : "Not initialized"
            ),
            React.createElement("p", { className: "text-xs text-muted-foreground mt-0.5" },
              statusError ? status.error
                : statusInitialized ? "Config: " + (status.config_path || "kanban-config.yaml") + ". Coding agent: " + (status.coding_agent || "agent") + "."
                : "Run bootstrap to provision profiles, config, and cron scripts."
            )
          )
        )
      ),

      // ── Project ──
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Project")
        ),
        React.createElement(CardContent, { className: "space-y-4" },
          React.createElement("div", { className: "space-y-1.5" },
            React.createElement(Label, { className: "text-xs" }, "Working branch"),
            React.createElement(Input, { value: workingBranch, onChange: function (e) { setWorkingBranch(e.target.value); }, placeholder: "main", className: "h-9" }),
            React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Integration branch where completed worktree commits are merged.")
          )
        )
      ),

      // ── Coding agent ──
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Coding Agent")
        ),
        React.createElement(CardContent, { className: "space-y-4" },
          React.createElement("div", { className: "space-y-1.5" },
            React.createElement(Label, { className: "text-xs" }, "Binary on PATH"),
            React.createElement("select", {
              value: codingAgent,
              onChange: function (e) { setCodingAgent(e.target.value); },
              className: "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            },
              CODING_AGENTS.map(function (a) {
                return React.createElement("option", { key: a.value, value: a.value }, a.label);
              })
            ),
            React.createElement("p", { className: "text-[11px] text-muted-foreground" },
              "The headless CLI coding agent workers will dispatch. ",
              React.createElement("a", { href: "https://github.com/thebizfixer/hermes-kanban-advanced-workflow/blob/main/docs/reference/coding-agents.md", target: "_blank", className: "underline" }, "Supported agents")
            )
          ),
          codingAgent === "__custom__" ? React.createElement("div", { className: "space-y-1.5" },
            React.createElement(Label, { className: "text-xs" }, "Custom binary name"),
            React.createElement(Input, { value: customAgent, onChange: function (e) { setCustomAgent(e.target.value); }, placeholder: "e.g. my-agent", className: "h-9" })
          ) : null
        )
      ),

      // ── Profiles ──
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Profiles")
        ),
        React.createElement(CardContent, { className: "space-y-2" },
          React.createElement("div", { className: "flex items-center justify-between py-1.5 px-3 rounded-md border" },
            React.createElement("span", { className: "text-sm" }, "orchestrator"),
            profileBadge(status && status.profiles && status.profiles.orchestrator)
          ),
          React.createElement("div", { className: "flex items-center justify-between py-1.5 px-3 rounded-md border" },
            React.createElement("span", { className: "text-sm" }, "worker"),
            profileBadge(status && status.profiles && status.profiles.worker)
          ),
          React.createElement("p", { className: "text-[11px] text-muted-foreground mt-1" }, "Profiles are created by bootstrap if missing. Model config is copied from the current profile.")
        )
      ),

      // ── Orchestrator tuning ──
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Orchestrator Tuning")
        ),
        React.createElement(CardContent, { className: "space-y-4" },
          React.createElement("div", { className: "space-y-1.5" },
            React.createElement(Label, { className: "text-xs" }, "Max turns"),
            React.createElement(Input, { type: "number", value: maxTurns, onChange: function (e) { setMaxTurns(e.target.value); }, min: 90, max: 500, className: "h-9" }),
            React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Recommended 180 for complex plan decomposition. Hermes default is 90.")
          )
        )
      ),

      // ── Gateway ──
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Gateway")
        ),
        React.createElement(CardContent, null,
          React.createElement("div", { className: "flex items-center justify-between py-1.5 px-3 rounded-md border" },
            React.createElement("span", { className: "text-sm" }, "hermes gateway"),
            gatewayBadge(status && status.gateway)
          )
        )
      ),

      // ── Actions ──
      React.createElement("div", { className: "flex gap-2" },
        React.createElement(Button, { onClick: runBootstrap, disabled: bootstrapping, className: "gap-2" },
          bootstrapping ? "Running…" : "Bootstrap"
        ),
        initialized ? React.createElement(Button, { variant: "outline", onClick: runUpdate, disabled: bootstrapping },
          "Update settings"
        ) : null
      ),

      // ── Console output ──
      consoleLines.length > 0 ? React.createElement(Card, { className: "bg-black/50" },
        React.createElement(CardContent, { className: "py-3" },
          React.createElement("pre", { className: "text-xs font-mono text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto" },
            consoleLines.map(function (line, i) {
              return React.createElement("div", { key: i, className: line.cls === "line-ok" ? "text-green-400" : line.cls === "line-warn" ? "text-yellow-400" : line.cls === "line-err" ? "text-red-400" : "" }, line.text);
            })
          )
        )
      ) : null
    );
  }

  // ── Register tab ──
  var plugins = window.__HERMES_PLUGINS__;
  if (plugins && plugins.register) {
    plugins.register("kanban-advanced", KanbanAdvancedPage);
    console.log("[kanban-advanced] Dashboard tab registered");
  } else {
    console.error("[kanban-advanced] Plugin registration API not found");
  }
})();
