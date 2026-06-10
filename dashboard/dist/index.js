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

  // ── API helpers ──
  function apiFetch(path, opts) {
    opts = opts || {};
    opts.credentials = "include";
    opts.headers = opts.headers || {};
    opts.headers["Content-Type"] = "application/json";
    var token = window.__HERMES_SESSION_TOKEN__;
    if (token) {
      opts.headers["X-Hermes-Session-Token"] = token;
    }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var msg = body.error || body.detail || ("HTTP " + r.status);
          if (typeof msg !== "string") msg = JSON.stringify(msg);
          throw new Error(msg);
        }
        return body;
      });
    });
  }
  function apiStatus() { return apiFetch("/api/plugins/kanban-advanced/status"); }
  function apiInit(data) { return apiFetch("/api/plugins/kanban-advanced/init", { method: "POST", body: JSON.stringify(data) }); }
  function apiSave(data) { return apiFetch("/api/plugins/kanban-advanced/save", { method: "POST", body: JSON.stringify(data) }); }
  function apiPluginUpdate() { return apiFetch("/api/plugins/kanban-advanced/update", { method: "POST" }); }

  var POLICY_PROFILES = [
    { value: "balanced", label: "balanced — block violations (default)" },
    { value: "advisory", label: "advisory — warn only, human-supervised" },
    { value: "strict", label: "strict — block + notify, walk-away runs" }
  ];

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
      : props.status === "err" ? "bg-red-500"
      : "bg-muted-foreground/30";
    return React.createElement("span", { className: cn("inline-block w-2 h-2 rounded-full flex-shrink-0", color) });
  }

  // ── Main page ──
  function KanbanAdvancedPage() {
    var _useState = useState(null), status = _useState[0], setStatus = _useState[1];
    var _useState2 = useState(false), loading = _useState2[0], setLoading = _useState2[1];
    var _useState3 = useState(""), workingBranch = _useState3[0], setWorkingBranch = _useState3[1];
    var _useState3b = useState(""), triggerBranch = _useState3b[0], setTriggerBranch = _useState3b[1];
    var _useState4 = useState("agent"), codingAgent = _useState4[0], setCodingAgent = _useState4[1];
    var _useState5 = useState(""), customAgent = _useState5[0], setCustomAgent = _useState5[1];
    var _useState6 = useState(180), maxTurns = _useState6[0], setMaxTurns = _useState6[1];
    var _useState6b = useState("balanced"), policyProfile = _useState6b[0], setPolicyProfile = _useState6b[1];
    var _useState7 = useState([]), consoleLines = _useState7[0], setConsoleLines = _useState7[1];
    var _useState8 = useState(false), bootstrapping = _useState8[0], setBootstrapping = _useState8[1];
    var _useState9 = useState(false), initialized = _useState9[0], setInitialized = _useState9[1];
    var _useState10 = useState(null), editingProfile = _useState10[0], setEditingProfile = _useState10[1];
    var _useState11 = useState(null), modelOptions = _useState11[0], setModelOptions = _useState11[1];
    var _useState12 = useState(false), changingModel = _useState12[0], setChangingModel = _useState12[1];
    var _useState13 = useState(null), selectedProvider = _useState13[0], setSelectedProvider = _useState13[1];
    var _useState14 = useState(null), selectedModel = _useState14[0], setSelectedModel = _useState14[1];
    // selectedModel is {provider: string, model: string} | null
    var _useState15 = useState(""), modelQuery = _useState15[0], setModelQuery = _useState15[1];
    var _useState16 = useState(false), pluginUpdating = _useState16[0], setPluginUpdating = _useState16[1];

    function loadStatus() {
      apiStatus().then(function (s) {
        setStatus(s);
        if (s.config_exists) setInitialized(true);
        if (s.working_branch) setWorkingBranch(s.working_branch);
        else if (s.default_working_branch) setWorkingBranch(s.default_working_branch);
        if (s.trigger_branch) setTriggerBranch(s.trigger_branch);
        else setTriggerBranch("");
        if (s.coding_agent) {
          var found = CODING_AGENTS.some(function (a) { return a.value === s.coding_agent; });
          if (found) setCodingAgent(s.coding_agent);
          else { setCodingAgent("__custom__"); setCustomAgent(s.coding_agent); }
        }
        if (s.max_turns) setMaxTurns(s.max_turns);
        if (s.policy_profile) setPolicyProfile(s.policy_profile);
      }).catch(function (e) {
        setStatus({ error: e.message || "API unreachable" });
      });
    }

    useEffect(function () { loadStatus(); }, []);

    function formatTriggerBranch(value) {
      var v = (value || "").trim();
      return v ? v : "(none — optional)";
    }

    function getFormData() {
      var agent = codingAgent === "__custom__" ? (customAgent.trim() || "agent") : codingAgent;
      return {
        working_branch: workingBranch.trim() || (status && status.default_working_branch) || "main",
        coding_agent_binary: agent,
        max_turns: parseInt(maxTurns) || 180,
        trigger_branch: triggerBranch.trim(),
        policy_profile: policyProfile
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
      addLines(["=== Bootstrap starting ===", "Working branch: " + data.working_branch, "Trigger branch: " + formatTriggerBranch(data.trigger_branch), "Governance profile: " + data.policy_profile, "Coding agent: " + data.coding_agent_binary, "Max turns: " + data.max_turns, ""]);
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

    function runSave() {
      setBootstrapping(true);
      setConsoleLines([]);
      var data = getFormData();
      addLines(["=== Saving settings ===", "Working branch: " + data.working_branch, "Trigger branch: " + formatTriggerBranch(data.trigger_branch), "Governance profile: " + data.policy_profile, "Coding agent: " + data.coding_agent_binary, "Max turns: " + data.max_turns, ""]);
      apiSave(data).then(function (r) {
        if (r.output) addLines(r.output);
        setBootstrapping(false);
        loadStatus();
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setBootstrapping(false);
      });
    }

    function runPluginUpdate() {
      setPluginUpdating(true);
      setConsoleLines([]);
      addLines(["=== Updating plugin (git pull) ===", ""]);
      apiPluginUpdate().then(function (r) {
        if (r.error) {
          addLines(["ERROR: " + r.error], "line-err");
          if (r.output) addLines(r.output);
        } else {
          if (r.output) {
            var outLines = Array.isArray(r.output) ? r.output : String(r.output).split("\n");
            addLines(outLines);
          }
          addLines([r.unchanged ? "OK Plugin already up to date" : "OK Plugin updated"], "line-ok");
        }
        setPluginUpdating(false);
        loadStatus();
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setPluginUpdating(false);
      });
    }

    function initializedLabel() {
      if (!statusInitialized) return "Not initialized";
      if (status && status.plugin_can_update && status.plugin_up_to_date === true) return "Initialized (Up-to-date)";
      if (status && status.plugin_can_update && status.plugin_update_available) return "Initialized (Update Plugin)";
      return "Initialized";
    }

    var pluginUpdateDisabled = !status || !status.plugin_can_update || status.plugin_up_to_date === true
      || status.plugin_update_available !== true || pluginUpdating || bootstrapping;

    // ── Model selector ──
    function openModelPicker(profileName) {
      setEditingProfile(profileName);
      if (!modelOptions) {
        apiFetch("/api/model/options").then(function (opts) {
          setModelOptions(opts);
        }).catch(function () {
          setModelOptions({ error: true });
        });
      }
    }

    function setProfileModel(profileName, provider, model) {
      setChangingModel(true);
      apiFetch("/api/profiles/" + encodeURIComponent(profileName) + "/model", {
        method: "PUT",
        body: JSON.stringify({ provider: provider, model: model })
      }).then(function () {
        setEditingProfile(null);
        setChangingModel(false);
        loadStatus();
      }).catch(function (e) {
        setChangingModel(false);
        addLines(["ERROR setting model: " + e.message], "line-err");
      });
    }

    // ── Render helpers ──
    function profileBadge(info) {
      var inConfig = info && info.exists && info.has_model;
      var dotColor, labelText, labelColor;
      if (!inConfig) {
        dotColor = "#ef4444";
        labelText = info && info.exists ? "no model" : "not found";
        labelColor = "#f87171";
      } else if (info.model_reachable === true) {
        dotColor = "#22c55e";
        labelText = "reachable (" + (info.model || "?") + ")";
        labelColor = "#22c55e";
      } else if (info.model_reachable === false) {
        dotColor = "#eab308";
        labelText = "auth stale (" + (info.model || "?") + ")";
        labelColor = "#eab308";
      } else {
        dotColor = "#eab308";
        labelText = "configured (" + (info.model || "?") + ")";
        labelColor = "#eab308";
      }
      return React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "6px" } },
        React.createElement("span", { style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: dotColor, flexShrink: 0 } }),
        React.createElement("span", { style: { fontSize: "12px", color: labelColor } }, labelText)
      );
    }

    var statusInitialized = status && status.config_exists;
    var statusError = status && status.error;
    var statusLoading = status === null;

    // ── Loading state ──
    if (statusLoading) {
      return React.createElement("div", { className: "flex items-center justify-center py-16" },
        React.createElement("div", { className: "flex flex-col items-center gap-3 text-muted-foreground" },
          React.createElement("div", { className: "w-5 h-5 border-2 border-muted-foreground/30 border-t-primary rounded-full animate-spin" }),
          React.createElement("span", { className: "text-xs" }, "Loading settings…")
        )
      );
    }

    return React.createElement("div", { className: "space-y-6" },

      // ── Status banner with inline buttons ──
      React.createElement(Card, { className: statusError ? "border-red-500/30" : statusInitialized ? "border-green-500/30" : "" },
        React.createElement(CardContent, { className: "flex items-start gap-3 py-4" },
          React.createElement(StatusDot, { status: statusError ? "error" : statusInitialized ? "ok" : "warn" }),
          React.createElement("div", { className: "flex-1 min-w-0 space-y-1" },
            React.createElement("p", { className: "text-sm font-medium" },
              statusError ? "Cannot reach API" : initializedLabel()
            ),
            React.createElement("p", { className: "text-xs text-muted-foreground truncate" },
              statusError ? status.error
                : statusInitialized ? "Config: " + (status.config_path || "kanban-config.yaml")
                : "Run bootstrap to provision profiles, config, and cron scripts."
            ),
            !statusError ? React.createElement("p", { className: "text-[11px] text-muted-foreground leading-snug" },
              "Bootstrap to run hermes kanban-advanced init with the following parameters. Save any parameter changes to plugin configuration after editing any field."
            ) : null
          ),
          React.createElement("div", { className: "flex items-center gap-2 shrink-0" },
            React.createElement(Button, { onClick: runBootstrap, disabled: bootstrapping || pluginUpdating, size: "sm" },
              bootstrapping ? "Running…" : "Bootstrap"
            ),
            initialized ? React.createElement(Button, { variant: "outline", size: "sm", onClick: runSave, disabled: bootstrapping || pluginUpdating },
              "Save"
            ) : null,
            status && status.plugin_can_update ? React.createElement(Button, {
              variant: "outline",
              size: "sm",
              onClick: runPluginUpdate,
              disabled: pluginUpdateDisabled
            },
              pluginUpdating
                ? React.createElement("span", { className: "flex items-center gap-1.5" },
                    React.createElement("span", { className: "w-3 h-3 border border-current border-t-transparent rounded-full animate-spin flex-shrink-0" }),
                    "Updating…"
                  )
                : "Update Plugin"
            ) : null
          )
        )
      ),

      // ── Two-column grid ──
      React.createElement("div", { className: "grid grid-cols-2 gap-4" },

        // Left column
        React.createElement("div", { className: "space-y-4" },

          // Project
          React.createElement(Card, null,
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Project")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Working branch"),
                React.createElement(Input, { value: workingBranch, onChange: function (e) { setWorkingBranch(e.target.value); }, placeholder: "main", className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Integration branch for worktree commits. Defaults to your git checkout / origin default.")
              ),
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Trigger branch"),
                React.createElement(Input, { value: triggerBranch, onChange: function (e) { setTriggerBranch(e.target.value); }, placeholder: "Optional", className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "The protected branch agents should NOT push to. Optional.")
              )
            )
          ),

          // Profiles
          React.createElement(Card, null,
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Profiles")
            ),
            React.createElement(CardContent, { className: "space-y-2" },
              React.createElement("div", { className: "flex items-center justify-between py-1.5 px-3 rounded-md border hover:bg-accent/5 cursor-pointer transition-colors", onClick: function () { openModelPicker("orchestrator"); } },
                React.createElement("span", { className: "text-sm" }, "orchestrator"),
                profileBadge(status && status.profiles && status.profiles.orchestrator)
              ),
              React.createElement("div", { className: "flex items-center justify-between py-1.5 px-3 rounded-md border hover:bg-accent/5 cursor-pointer transition-colors", onClick: function () { openModelPicker("worker"); } },
                React.createElement("span", { className: "text-sm" }, "worker"),
                profileBadge(status && status.profiles && status.profiles.worker)
              ),
              React.createElement("p", { className: "text-[11px] text-muted-foreground mt-1" }, "Created by bootstrap if missing. Model config copied from current profile. Click profile to change model.")
            )
          ),
          // ── Model picker modal (dropdown menu) ──
          editingProfile ? React.createElement("div", {
            className: "fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4",
            onClick: function (e) { if (e.target === e.currentTarget) setEditingProfile(null); }
          },
            React.createElement("div", {
              className: "relative w-full max-w-sm border border-border bg-card shadow-2xl flex flex-col overflow-hidden",
              onClick: function (e) { e.stopPropagation(); }
            },
              // Close button
              React.createElement("button", {
                onClick: function () { setEditingProfile(null); setSelectedModel(null); },
                className: "absolute right-2 top-2 w-7 h-7 flex items-center justify-center rounded-md hover:bg-accent/20 text-muted-foreground hover:text-foreground transition-colors z-10",
                "aria-label": "Close"
              }, "✕"),

              // Header
              React.createElement("header", { className: "p-4 pb-3 border-b border-border" },
                React.createElement("h2", { className: "text-sm font-semibold tracking-wide" }, "Change model — " + editingProfile)
              ),

              // Dropdown list
              React.createElement("div", { className: "overflow-y-auto max-h-64" },
                !modelOptions ? React.createElement("div", { className: "p-4 text-xs text-muted-foreground" }, "Loading…")
                : modelOptions.error ? React.createElement("div", { className: "p-4 text-xs text-red-400" }, "Could not load")
                : (modelOptions.providers || []).map(function (prov) {
                    var provName = prov.name || prov;
                    var provModels = prov.models || [];
                    if (!provModels.length) return null;
                    return React.createElement("div", { key: provName || prov },
                      React.createElement("div", { className: "px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide bg-muted/30" }, provName),
                      provModels.map(function (m) {
                        var modelId = typeof m === "string" ? m : m.id || m.name;
                        var modelLabel = typeof m === "string" ? m : m.name || m.id;
                        var isCurrent = status && status.profiles && status.profiles[editingProfile] && status.profiles[editingProfile].model === modelId;
                        var isSel = selectedModel && selectedModel.model === modelId && selectedModel.provider === provName;
                        return React.createElement("div", {
                          key: modelId,
                          className: "flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer hover:bg-accent/10 transition-colors" + (isSel ? " bg-accent/10" : ""),
                          onClick: function () { setSelectedModel({ provider: provName, model: modelId }); }
                        },
                          React.createElement("span", { className: "w-3 h-3 shrink-0 flex items-center justify-center text-[10px]" }, isSel ? "✓" : ""),
                          React.createElement("span", { className: "flex-1 truncate font-mono" }, modelLabel),
                          isCurrent ? React.createElement("span", { className: "text-[10px] text-primary shrink-0" }, "current") : null
                        );
                      })
                    );
                  })
              ),

              // Footer
              React.createElement("footer", { className: "border-t border-border p-3 flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-[11px] text-muted-foreground" }, selectedModel ? selectedModel.model : "Select a model"),
                React.createElement("div", { className: "flex items-center gap-1.5" },
                  React.createElement(Button, { variant: "outline", size: "sm", onClick: function () { setEditingProfile(null); setSelectedModel(null); } }, "Cancel"),
                  React.createElement(Button, {
                    size: "sm",
                    disabled: !selectedModel || changingModel,
                    onClick: function () { if (selectedModel) setProfileModel(editingProfile, selectedModel.provider, selectedModel.model); }
                  }, changingModel ? "…" : "Switch")
                )
              )
            )
          ) : null
        ),

        // Right column
        React.createElement("div", { className: "space-y-4" },

          // Coding agent
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
                  "Workers dispatch this binary. ",
                  React.createElement("a", { href: "https://github.com/thebizfixer/hermes-kanban-advanced-workflow/blob/main/docs/reference/coding-agents.md", target: "_blank", className: "underline" }, "Supported agents")
                )
              ),
              codingAgent === "__custom__" ? React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Custom binary name"),
                React.createElement(Input, { value: customAgent, onChange: function (e) { setCustomAgent(e.target.value); }, placeholder: "e.g. my-agent", className: "h-9" })
              ) : null
            )
          ),

          // Governance + orchestrator tuning
          React.createElement(Card, null,
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Governance & Tuning")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Governance profile"),
                React.createElement("select", {
                  value: policyProfile,
                  onChange: function (e) { setPolicyProfile(e.target.value); },
                  className: "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                },
                  POLICY_PROFILES.map(function (p) {
                    return React.createElement("option", { key: p.value, value: p.value }, p.label);
                  })
                ),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Controls card policy, evaluation chain, and validation gates. Use strict for walk-away execution.")
              ),
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Max turns"),
                React.createElement(Input, { type: "number", value: maxTurns, onChange: function (e) { setMaxTurns(e.target.value); }, min: 90, max: 500, className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Recommended 180 for plan decomposition. Default is 90.")
              )
            )
          )
        )
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
