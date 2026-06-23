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
  var useRef = SDK.hooks.useRef;
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

  // ── Environment detection ──
  var IS_LOCALHOST = window.location.hostname === "localhost" 
                  || window.location.hostname === "127.0.0.1"
                  || window.location.hostname === "[::1]";
  var API_BASE = IS_LOCALHOST 
    ? "http://127.0.0.1:" + (window.__KA_DASHBOARD_PORT__ || "18900")
    : "";

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
    return fetch(path.indexOf("/api/plugins/kanban-advanced/") === 0 ? API_BASE + path : path, opts).then(function (r) {
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
  var STATUS_SESSION_KEY = "kanban-advanced-status-v1";

  function readSessionStatus() {
    try {
      var raw = sessionStorage.getItem(STATUS_SESSION_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || !parsed.data) return null;
      return parsed;
    } catch (e) {
      return null;
    }
  }

  function writeSessionStatus(data, opts) {
    opts = opts || {};
    try {
      var prev = readSessionStatus();
      var probeGreen = opts.probeGreen;
      if (probeGreen == null && opts.probed && data) {
        probeGreen = statusProbeAllGreen(data);
      } else if (opts.keepProbeGreen && prev) {
        probeGreen = prev.probeGreen;
      } else if (probeGreen == null && prev) {
        probeGreen = !!prev.probeGreen;
      }
      sessionStorage.setItem(STATUS_SESSION_KEY, JSON.stringify({
        data: data,
        at: Date.now(),
        probedAt: opts.probed ? Date.now() : (opts.keepProbedAt || (prev && prev.probedAt) || 0),
        probeGreen: !!probeGreen
      }));
    } catch (e) {}
  }

  function statusProbeAllGreen(s) {
    if (!s || s.error) return false;
    var cli = s.coding_agent_cli || {};
    if (cli.on_path === false) return false;
    if (cli.on_path && cli.model_reachable !== true) return false;
    var profiles = s.profiles || {};
    for (var k in profiles) {
      if (!Object.prototype.hasOwnProperty.call(profiles, k)) continue;
      var p = profiles[k];
      if (p && p.exists && p.has_model && p.model_reachable !== true) return false;
    }
    return true;
  }

  function sessionProbeGreenCached(cached) {
    return !!(cached && cached.probedAt && cached.probeGreen);
  }

  function invalidateSessionStatus() {
    try { sessionStorage.removeItem(STATUS_SESSION_KEY); } catch (e) {}
  }

  function applyPluginGitStatus(prev, fields) {
    if (!fields) return prev;
    var next = Object.assign({}, prev || {});
    ["plugin_can_update", "plugin_up_to_date", "plugin_behind", "plugin_update_available", "plugin_local_changes"].forEach(function (key) {
      if (fields[key] != null) next[key] = fields[key];
    });
    if (fields.hermes_home) next.hermes_home = fields.hermes_home;
    if (fields.plugin_install_path) next.plugin_install_path = fields.plugin_install_path;
    return next;
  }

  function mergeStatusFields(base, extra) {
    if (!extra) return base;
    if (!base) return extra;
    var merged = Object.assign({}, base, extra);
    ["plugin_up_to_date", "plugin_behind", "plugin_update_available", "plugin_local_changes"].forEach(function (key) {
      if (extra[key] == null && base[key] != null) merged[key] = base[key];
    });
    if (base.profiles && extra.profiles) {
      merged.profiles = Object.assign({}, base.profiles);
      Object.keys(extra.profiles).forEach(function (k) {
        var prev = base.profiles[k] || {};
        var next = extra.profiles[k] || {};
        merged.profiles[k] = Object.assign({}, prev, next);
        if (next.model_reachable == null && prev.model_reachable != null) {
          merged.profiles[k].model_reachable = prev.model_reachable;
        }
        if (!next.model_reachability_detail && prev.model_reachability_detail) {
          merged.profiles[k].model_reachability_detail = prev.model_reachability_detail;
        }
      });
    }
    if (extra.coding_agent_model == null && base.coding_agent_model != null) {
      merged.coding_agent_model = base.coding_agent_model;
    }
    if (extra.coding_agent == null && base.coding_agent != null) {
      merged.coding_agent = base.coding_agent;
    }
    if (base.coding_agent_cli && extra.coding_agent_cli) {
      merged.coding_agent_cli = Object.assign({}, base.coding_agent_cli, extra.coding_agent_cli);
      if (extra.coding_agent_cli.model_reachable == null && base.coding_agent_cli.model_reachable != null) {
        merged.coding_agent_cli.model_reachable = base.coding_agent_cli.model_reachable;
      }
    }
    return merged;
  }

  function apiStatus(query) {
    var q = query ? ("?" + query) : "";
    return apiFetch("/api/plugins/kanban-advanced/status" + q);
  }
  function apiCodingAgentModels(binary) {
    return apiFetch("/api/plugins/kanban-advanced/coding-agent/models?binary=" + encodeURIComponent(binary));
  }
  function apiInit(data) { return apiFetch("/api/plugins/kanban-advanced/init", { method: "POST", body: JSON.stringify(data) }); }
  function apiSave(data) { return apiFetch("/api/plugins/kanban-advanced/save", { method: "POST", body: JSON.stringify(data) }); }
  function apiPluginUpdate() { return apiFetch("/api/plugins/kanban-advanced/update", { method: "POST" }); }
  function apiPutProfile(profileName, data) {
    return apiFetch("/api/plugins/kanban-advanced/profiles/" + encodeURIComponent(profileName), {
      method: "PUT",
      body: JSON.stringify(data)
    });
  }
  function apiProbeProfile(profileName) {
    return apiFetch("/api/plugins/kanban-advanced/profiles/" + encodeURIComponent(profileName) + "/probe", { method: "POST" });
  }

  var REASONING_EFFORT_LEVELS = [
    "none", "low", "minimal", "medium", "high", "xhigh"
  ];

  var POLICY_PROFILES = [
    { value: "balanced", label: "balanced — block violations (default)" },
    { value: "advisory", label: "advisory — warn only, human-supervised" },
    { value: "strict", label: "strict — block + notify, walk-away runs" }
  ];

  var CUSTOM_CODING_AGENT_OPTION = {
    value: "__custom__",
    label: "Other (custom binary)…"
  };

  function buildCodingAgentOptions(status) {
    var rows = (status && status.available_coding_binaries) || [];
    var options = rows.map(function (b) {
      return { value: b.command, label: b.label };
    });
    options.push(CUSTOM_CODING_AGENT_OPTION);
    return options;
  }

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
    var _useState2 = useState(true), loading = _useState2[0], setLoading = _useState2[1];
    var _useState3 = useState(""), workingBranch = _useState3[0], setWorkingBranch = _useState3[1];
    var _useState3b = useState(""), triggerBranch = _useState3b[0], setTriggerBranch = _useState3b[1];
    var _useState4 = useState("hermes"), codingAgent = _useState4[0], setCodingAgent = _useState4[1];
    var _useState4b = useState(""), codingAgentModel = _useState4b[0], setCodingAgentModel = _useState4b[1];
    var _useState5 = useState(""), customAgent = _useState5[0], setCustomAgent = _useState5[1];
    var _useState6 = useState(180), maxTurns = _useState6[0], setMaxTurns = _useState6[1];
    var _useState6c = useState(false), maxTurnsTouched = _useState6c[0], setMaxTurnsTouched = _useState6c[1];
    var maxTurnsTouchedRef = useRef(false);
    var _useState6b = useState("balanced"), policyProfile = _useState6b[0], setPolicyProfile = _useState6b[1];
    var _useState7 = useState([]), consoleLines = _useState7[0], setConsoleLines = _useState7[1];
    var _useState8 = useState(false), bootstrapping = _useState8[0], setBootstrapping = _useState8[1];
    var _useState9 = useState(false), initialized = _useState9[0], setInitialized = _useState9[1];
    var _useState10 = useState(null), editingProfile = _useState10[0], setEditingProfile = _useState10[1];
    var _useState11 = useState(null), modelOptions = _useState11[0], setModelOptions = _useState11[1];
    var _useState12 = useState(null), savingProfile = _useState12[0], setSavingProfile = _useState12[1];
    var _useState13 = useState(null), selectedProvider = _useState13[0], setSelectedProvider = _useState13[1];
    var _useState14 = useState(null), selectedModel = _useState14[0], setSelectedModel = _useState14[1];
    // selectedModel is {provider: string, model: string} | null
    var _useState15 = useState(""), modelQuery = _useState15[0], setModelQuery = _useState15[1];
    var _useState16 = useState(false), pluginUpdating = _useState16[0], setPluginUpdating = _useState16[1];
    var _useState17 = useState(false), statusProbing = _useState17[0], setStatusProbing = _useState17[1];
    var _useState17b = useState(false), probesPending = _useState17b[0], setProbesPending = _useState17b[1];
    var _useState18 = useState(false), editingCodingAgentModel = _useState18[0], setEditingCodingAgentModel = _useState18[1];
    var _useState19 = useState(null), codingAgentModelOptions = _useState19[0], setCodingAgentModelOptions = _useState19[1];
    var _useState20 = useState(""), codingAgentModelQuery = _useState20[0], setCodingAgentModelQuery = _useState20[1];
    var _useState21 = useState(null), pendingCodingAgentModel = _useState21[0], setPendingCodingAgentModel = _useState21[1];
    var _useState22 = useState("medium"), pendingReasoningEffort = _useState22[0], setPendingReasoningEffort = _useState22[1];
    var _useState23 = useState("medium"), initialReasoningEffort = _useState23[0], setInitialReasoningEffort = _useState23[1];
    var _useState24 = useState(true), notifyLifecycle = _useState24[0], setNotifyLifecycle = _useState24[1];
    var _useState25 = useState(false), walkAwayMode = _useState25[0], setWalkAwayMode = _useState25[1];
    var _useState26 = useState(false), notifySaving = _useState26[0], setNotifySaving = _useState26[1];
    var _useState27 = useState([CUSTOM_CODING_AGENT_OPTION]), codingAgentOptions = _useState27[0], setCodingAgentOptions = _useState27[1];
    var _useState28 = useState(false), codingAgentTouched = _useState28[0], setCodingAgentTouched = _useState28[1];
    var codingAgentTouchedRef = useRef(false);
    var _useState29 = useState(false), workingBranchTouched = _useState29[0], setWorkingBranchTouched = _useState29[1];
    var workingBranchTouchedRef = useRef(false);
    var _useState30 = useState(false), triggerBranchTouched = _useState30[0], setTriggerBranchTouched = _useState30[1];
    var triggerBranchTouchedRef = useRef(false);
    var _useState31 = useState(false), policyTouched = _useState31[0], setPolicyTouched = _useState31[1];
    var policyTouchedRef = useRef(false);
    var _useState32 = useState(false), notifyTouched = _useState32[0], setNotifyTouched = _useState32[1];
    var notifyTouchedRef = useRef(false);
    var _useState33 = useState(false), walkawayTouched = _useState33[0], setWalkawayTouched = _useState33[1];
    var walkawayTouchedRef = useRef(false);
    var _useState34 = useState(null), probingProfile = _useState34[0], setProbingProfile = _useState34[1];

    function resolvedCodingBinary() {
      return codingAgent === "__custom__" ? (customAgent.trim() || "agent") : codingAgent;
    }

    function binaryRowFor(command) {
      var rows = (status && status.available_coding_binaries) || [];
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].command === command) return rows[i];
      }
      return null;
    }

    function codingAgentBinaryConflict(binary) {
      var row = binaryRowFor(binary);
      return !!(row && row.contested);
    }

    function codingAgentModelSelectionBlocked() {
      var binary = resolvedCodingBinary();
      if (!binary) return true;
      return codingAgentBinaryConflict(binary);
    }

    function codingAgentModelDisplay() {
      if (!codingAgentModel) return "(select a model)";
      if (codingAgentModel === "auto") {
        if (codingAgentModelOptions && codingAgentModelOptions._autoLabel) {
          return codingAgentModelOptions._autoLabel;
        }
        if (codingAgentModelOptions && codingAgentModelOptions.models && codingAgentModelOptions.models.length > 0) {
          return codingAgentModelOptions.models[0].label || "auto (profile config)";
        }
        return "auto (profile config)";
      }
      return codingAgentModel;
    }

    function validateCodingAgentSelection() {
      if (codingAgentModelSelectionBlocked()) {
        return "Resolve the binary symlink conflict before selecting a model (choose an unambiguous command such as cursor-agent).";
      }
      if (!codingAgentModel) {
        return "Select a model for " + resolvedCodingBinary() + " before Save or Bootstrap.";
      }
      return "";
    }

    function resetCodingAgentModelForBinary(binary) {
      if (!binary) return;
      // Hermes uses the profile config model by default — pre-select auto
      if (binary === "hermes") {
        setCodingAgentModel("auto");
      } else {
        setCodingAgentModel("");
      }
      setPendingCodingAgentModel(null);
      setCodingAgentModelQuery("");
      setCodingAgentModelOptions(null);
      // For hermes, the model catalog is loaded lazily in openCodingAgentModelPicker
      if (binary !== "hermes" && !codingAgentBinaryConflict(binary)) {
        apiCodingAgentModels(binary).then(function (opts) {
          setCodingAgentModelOptions(opts);
        }).catch(function () {
          setCodingAgentModelOptions({
            error: true,
            models: [{ id: "auto", label: "Auto (profile config)" }]
          });
        });
      }
    }

    function onCodingAgentBinaryChange(next) {
      setCodingAgent(next);
      setCodingAgentTouched(true);
      codingAgentTouchedRef.current = true;
      if (next === "__custom__") {
        setCodingAgentModel("");
        setCodingAgentModelOptions(null);
        setPendingCodingAgentModel(null);
        return;
      }
      resetCodingAgentModelForBinary(next);
    }

    function applyStatusToForm(s) {
      if (!s || s.error) return;
      if (s.config_exists) setInitialized(true);
      if (!workingBranchTouchedRef.current) {
        if (s.working_branch) setWorkingBranch(s.working_branch);
        else if (s.default_working_branch) setWorkingBranch(s.default_working_branch);
      }
      if (!triggerBranchTouchedRef.current) {
        if (s.trigger_branch) setTriggerBranch(s.trigger_branch);
        else setTriggerBranch("");
      }
      if (!codingAgentTouchedRef.current) {
        if (s.coding_agent) {
          var options = buildCodingAgentOptions(s);
          setCodingAgentOptions(options);
          var found = options.some(function (a) { return a.value === s.coding_agent; });
          if (found) setCodingAgent(s.coding_agent);
          else { setCodingAgent("__custom__"); setCustomAgent(s.coding_agent); }
        } else {
          setCodingAgentOptions(buildCodingAgentOptions(s));
        }
        if (s.coding_agent_model) setCodingAgentModel(s.coding_agent_model);
        else setCodingAgentModel("");
      }
      if (s.max_turns && !maxTurnsTouchedRef.current) setMaxTurns(s.max_turns);
      if (!policyTouchedRef.current) {
        if (s.policy_profile) setPolicyProfile(s.policy_profile);
      }
      if (!notifyTouchedRef.current) {
        if (typeof s.notify_lifecycle === "boolean") {
          setNotifyLifecycle(s.notify_lifecycle);
        } else if (s.notify_lifecycle != null) {
          setNotifyLifecycle(String(s.notify_lifecycle).toLowerCase() === "true" || s.notify_lifecycle === true);
        }
      }
      if (!walkawayTouchedRef.current) {
        if (typeof s.walk_away_mode === "boolean") {
          setWalkAwayMode(s.walk_away_mode);
        } else if (s.walk_away_mode != null) {
          setWalkAwayMode(String(s.walk_away_mode).toLowerCase() === "true" || s.walk_away_mode === true);
        } else if (typeof s.notify_on_complete === "boolean") {
          setWalkAwayMode(s.notify_on_complete);
        } else if (s.notify_on_complete != null) {
          setWalkAwayMode(String(s.notify_on_complete).toLowerCase() === "true" || s.notify_on_complete === true);
        }
      }
    }

    function loadStatus(opts) {
      opts = opts || {};
      var cached = opts.skipCache ? null : readSessionStatus();
      var sessionGreen = sessionProbeGreenCached(cached);
      var needProbe = opts.full !== false && (
        opts.forceFull ||
        !sessionGreen && (!(cached && cached.probedAt) || !cached.probeGreen)
      );
      var needGitFetch = opts.full !== false && !needProbe;

      if (needGitFetch) setStatusProbing(true);
      setLoading(true);
      return apiStatus().then(function (s) {
        var merged = cached && cached.data ? mergeStatusFields(cached.data, s) : s;
        setStatus(merged);
        if (!opts.skipApply) applyStatusToForm(merged);
        writeSessionStatus(merged, {
          keepProbedAt: sessionGreen ? cached.probedAt : 0,
          keepProbeGreen: sessionGreen
        });
        setLoading(false);

        // Always submit staggered probes on page load — the executor queue
        // serializes them so they can't flood the gateway
        var profiles = Object.keys(merged.profiles || {});
        var staggerDelay = 0;
        profiles.forEach(function (p) {
          setTimeout(function () {
            apiProbeProfile(p);
          }, staggerDelay);
          staggerDelay += 5000;
        });
        setTimeout(function () {
          apiFetch("/api/plugins/kanban-advanced/coding-agent/probe", { method: "POST" });
        }, staggerDelay);

        // Start polling for probe results after all probes have been submitted.
        // Probes run in a background ThreadPoolExecutor — poll /status until
        // results come back so dashboard badges update.
        var probeStaggerTotal = staggerDelay + 2000;
        setTimeout(function () {
          setProbesPending(true);
          var pollAttempts = 0;
          var maxPollAttempts = 15; // 30 seconds max
          var pollInterval = setInterval(function () {
            pollAttempts++;
            apiStatus().then(function (fresh) {
              var allProbed = true;
              var freshProfiles = fresh.profiles || {};
              Object.keys(freshProfiles).forEach(function (k) {
                var pinfo = freshProfiles[k];
                if (pinfo && pinfo.exists && pinfo.has_model && pinfo.model_reachable == null) {
                  allProbed = false;
                }
              });
              var cli = fresh.coding_agent_cli || {};
              if (cli.on_path && cli.model_reachable == null) {
                allProbed = false;
              }
              if (allProbed || pollAttempts >= maxPollAttempts) {
                clearInterval(pollInterval);
                setProbesPending(false);
              }
              setStatus(function (prev) {
                var complete = mergeStatusFields(prev, fresh);
                writeSessionStatus(complete, { probed: allProbed });
                return complete;
              });
            }).catch(function () {
              if (pollAttempts >= maxPollAttempts) {
                clearInterval(pollInterval);
                setProbesPending(false);
              }
            });
          }, 2000);
        }, probeStaggerTotal);

        if (needGitFetch) {
          return apiStatus("git_fetch=1").then(function (gitStatus) {
            var complete = mergeStatusFields(merged, gitStatus);
            setStatus(complete);
            if (!opts.skipApply) applyStatusToForm(complete);
            writeSessionStatus(complete, {
              keepProbedAt: sessionGreen && cached ? cached.probedAt : 0,
              keepProbeGreen: sessionGreen
            });
            setStatusProbing(false);
            return complete;
          }).catch(function () {
            setStatusProbing(false);
            return merged;
          });
        }

        return merged;
      }).catch(function (e) {
        setLoading(false);
        setStatusProbing(false);
        var msg = e.message || "API unreachable";
        if (msg === "Failed to fetch" || msg.indexOf("NetworkError") >= 0) {
          // Sidecar may be starting — poll health until it's up (keepalive cron restarts within 60s)
          setStatus({ error: "Sidecar server starting… (auto-recovery in progress)" });
          var attempts = 0;
          var healthInterval = setInterval(function () {
            attempts++;
            fetch("http://127.0.0.1:" + (window.__KA_DASHBOARD_PORT__ || "18900") + "/health")
              .then(function (r) {
                if (r.ok) {
                  clearInterval(healthInterval);
                  loadStatus();  // retry full load
                }
              })
              .catch(function () {});
            if (attempts >= 30) {  // 60s max
              clearInterval(healthInterval);
              msg = "Dashboard server not running on port " + (window.__KA_DASHBOARD_PORT__ || "18900") + ". Start it: python3 scripts/dashboard_server.py";
              setStatus({ error: msg });
            }
          }, 2000);
          return;
        }
        setStatus({ error: msg });
      });
    }

    function reloadStatus(opts) {
      invalidateSessionStatus();
      opts = opts || {};
      return loadStatus({ skipCache: true, forceFull: true, skipApply: opts.skipApply });
    }

    function pollUntilProbed(profileName) {
      var attempts = 0;
      var maxAttempts = 15;
      var interval = setInterval(function () {
        attempts++;
        if (attempts > maxAttempts) {
          clearInterval(interval);
          setProbingProfile(null);
          return;
        }
        apiStatus().then(function (s) {
          var info = s.profiles && s.profiles[profileName];
          if (info && info.model_reachable != null) {
            clearInterval(interval);
            setProbingProfile(null);
            setStatus(s);
          }
        }).catch(function () {
          if (attempts >= 3) {
            clearInterval(interval);
            setProbingProfile(null);
          }
        });
      }, 2000);
    }

    useEffect(function () { loadStatus(); }, []);

    function formatTriggerBranch(value) {
      var v = (value || "").trim();
      return v ? v : "(none — optional)";
    }

    function getFormData() {
      var agent = resolvedCodingBinary();
      return {
        working_branch: workingBranch.trim() || (status && status.default_working_branch) || "main",
        coding_agent_binary: agent,
        coding_agent_model: (codingAgentModel || "auto").trim() || "auto",
        max_turns: parseInt(maxTurns) || 180,
        trigger_branch: triggerBranch.trim(),
        policy_profile: policyProfile,
        notify_lifecycle: notifyLifecycle,
        walk_away_mode: walkAwayMode
      };
    }

    function saveSucceeded(r) {
      if (!r || r.error || r.success === false) {
        throw new Error((r && r.error) || "Save failed");
      }
      return r;
    }

    function persistNotifyLifecycle(next) {
      setNotifyLifecycle(next);
      if (!initialized) return;
      setNotifySaving(true);
      var data = getFormData();
      data.notify_lifecycle = next;
      apiSave(data).then(saveSucceeded).then(function () {
        reloadStatus({ skipApply: true });
      }).catch(function (e) {
        setNotifyLifecycle(!next);
        addLines(["ERROR: " + e.message], "line-err");
      }).finally(function () {
        setNotifySaving(false);
      });
    }

    function persistWalkAwayMode(next) {
      setWalkAwayMode(next);
      if (!initialized) return;
      setNotifySaving(true);
      var data = getFormData();
      data.walk_away_mode = next;
      apiSave(data).then(saveSucceeded).then(function () {
        reloadStatus({ skipApply: true });
      }).catch(function (e) {
        setWalkAwayMode(!next);
        addLines(["ERROR: " + e.message], "line-err");
      }).finally(function () {
        setNotifySaving(false);
      });
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
      var agentErr = validateCodingAgentSelection();
      if (agentErr) {
        addLines(["ERROR: " + agentErr], "line-err");
        setBootstrapping(false);
        return;
      }
      var data = getFormData();
      addLines(["=== Bootstrap starting ===", "Working branch: " + data.working_branch, "Trigger branch: " + formatTriggerBranch(data.trigger_branch), "Governance profile: " + data.policy_profile, "Coding agent: " + data.coding_agent_binary + " (" + data.coding_agent_model + ")", "Max turns: " + data.max_turns, ""]);
      apiInit(data).then(function (r) {
        if (r.error || r.success === false) {
          addLines(["ERROR: " + (r.error || "Bootstrap failed")], "line-err");
          if (r.output) addLines(r.output);
        } else if (r.output) {
          addLines(r.output);
          if (r.success) {
            setInitialized(true);
          }
        }
        setBootstrapping(false);
        reloadStatus().then(function () {
          if (status && status.dispatch_profiles) {
            pollUntilProbed(status.dispatch_profiles.worker);
            pollUntilProbed(status.dispatch_profiles.orchestrator);
          }
        });
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setBootstrapping(false);
      });
    }

    function runSave() {
      setBootstrapping(true);
      setConsoleLines([]);
      var agentErr = validateCodingAgentSelection();
      if (agentErr) {
        addLines(["ERROR: " + agentErr], "line-err");
        setBootstrapping(false);
        return;
      }
      var data = getFormData();
      addLines(["=== Saving settings ===", "Working branch: " + data.working_branch, "Trigger branch: " + formatTriggerBranch(data.trigger_branch), "Governance profile: " + data.policy_profile, "Coding agent: " + data.coding_agent_binary + " (" + data.coding_agent_model + ")", "Max turns: " + data.max_turns, ""]);
      apiSave(data).then(saveSucceeded).then(function (r) {
        if (r.output) addLines(r.output);
        setBootstrapping(false);
        reloadStatus().then(function () {
          if (status && status.dispatch_profiles) {
            pollUntilProbed(status.dispatch_profiles.worker);
            pollUntilProbed(status.dispatch_profiles.orchestrator);
          }
        });
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
          setPluginUpdating(false);
          return;
        }
        if (r.output) {
          var outLines = Array.isArray(r.output) ? r.output : String(r.output).split("\n");
          addLines(outLines);
        }
        addLines([r.unchanged ? "OK Plugin already up to date" : "OK Plugin updated"], "line-ok");
        setStatus(function (prev) {
          var next = applyPluginGitStatus(prev, r);
          writeSessionStatus(next, { probed: true });
          return next;
        });
        setPluginUpdating(false);
      }).catch(function (e) {
        addLines(["ERROR: " + e.message], "line-err");
        setPluginUpdating(false);
      });
    }

    function initializedLabel() {
      if (!statusInitialized) return "Not initialized";
      if (statusProbing) return "Initialized (Checking for updates)";
      if (status && status.plugin_can_update && status.plugin_up_to_date === true) return "Initialized (Up-to-date)";
      if (status && status.plugin_can_update && status.plugin_update_available) return "Initialized (Update Plugin)";
      return "Initialized";
    }

    var pluginUpdateDisabled = !status || !status.plugin_can_update || status.plugin_up_to_date === true
      || pluginUpdating || bootstrapping || statusProbing;

    // ── Model selector ──
    function openModelPicker(profileName) {
      setEditingProfile(profileName);
      var profileInfo = status && status.profiles && status.profiles[profileName];
      var effort = (profileInfo && profileInfo.reasoning_effort) || "medium";
      setPendingReasoningEffort(effort);
      setInitialReasoningEffort(effort);
      setSelectedModel(null);
      if (!modelOptions) {
        apiFetch("/api/model/options").then(function (opts) {
          setModelOptions(opts);
        }).catch(function () {
          setModelOptions({ error: true });
        });
      }
    }

    function openCodingAgentModelPicker() {
      if (codingAgentModelSelectionBlocked()) return;
      var binary = resolvedCodingBinary();
      setPendingCodingAgentModel(codingAgentModel || null);
      setCodingAgentModelQuery("");
      setEditingCodingAgentModel(true);
      if (binary === "hermes") {
        // Hermes: merge sidecar (profile-aware auto label) + dashboard (full catalog)
        var sidecarPromise = apiCodingAgentModels("hermes").catch(function () { return null; });
        var catalogPromise = apiFetch("/api/model/options").catch(function () { return null; });
        Promise.all([sidecarPromise, catalogPromise]).then(function (_a) {
          var sidecar = _a[0], catalog = _a[1];
          var autoLabel = (sidecar && sidecar.models && sidecar.models[0] && sidecar.models[0].label) || "Auto (profile config)";
          var result = catalog && catalog.providers
            ? { providers: catalog.providers, source: "catalog", _autoLabel: autoLabel }
            : (sidecar || { error: true, models: [{ id: "auto", label: autoLabel }] });
          setCodingAgentModelOptions(result);
        });
      } else {
        apiCodingAgentModels(binary).then(function (opts) {
          setCodingAgentModelOptions(opts);
        }).catch(function () {
          setCodingAgentModelOptions({ error: true, models: [{ id: "auto", label: "Auto (CLI default)" }] });
        });
      }
    }

    function applyCodingAgentModelChoice() {
      if (!pendingCodingAgentModel) return;
      setCodingAgentModel(pendingCodingAgentModel);
      setCodingAgentTouched(true);
      codingAgentTouchedRef.current = true;
      setEditingCodingAgentModel(false);
      setPendingCodingAgentModel(null);
    }

    function profileEffortSuffix(info) {
      if (!info || !info.reasoning_effort) return "";
      if (info.reasoning_effort === "medium" && info.reasoning_effort_configured === false) return "";
      return " · " + info.reasoning_effort;
    }

    function profileApplyEnabled() {
      if (probingProfile === editingProfile) return false;
      var reasoningDirty = pendingReasoningEffort !== initialReasoningEffort;
      return Boolean(selectedModel) || reasoningDirty;
    }

    function applyProfileSettings(profileName) {
      var body = {};
      if (selectedModel) {
        body.provider = selectedModel.provider;
        body.model = selectedModel.model;
      }
      if (pendingReasoningEffort !== initialReasoningEffort) {
        body.reasoning_effort = pendingReasoningEffort;
      }
      if (!Object.keys(body).length) return;

      // Close modal immediately — save + probe happens in background
      var newModelName = selectedModel ? selectedModel.model : null;
      var newEffort = pendingReasoningEffort !== initialReasoningEffort ? pendingReasoningEffort : null;
      setEditingProfile(null);
      setSelectedModel(null);
      setSavingProfile(profileName);
      apiPutProfile(profileName, body).then(function () {
        setSavingProfile(null);
        setProbingProfile(profileName);
        return apiProbeProfile(profileName);
      }).then(function () {
        pollUntilProbed(profileName);
      }).catch(function (e) {
        setSavingProfile(null);
        setProbingProfile(null);
        addLines(["ERROR updating profile: " + e.message], "line-err");
      });
    }

    // ── Render helpers ──
    function codingAgentBadge(cli, modelId) {
      var info = cli || {};
      var model = modelId || codingAgentModel || "auto";
      var dotColor, labelText, labelColor;
      if (info.conflict) {
        dotColor = "#eab308";
        labelText = "symlink conflict";
        labelColor = "#eab308";
      } else if (!info.on_path) {
        dotColor = "#ef4444";
        labelText = "binary not on PATH";
        labelColor = "#f87171";
      } else if (info.model_reachable === true) {
        dotColor = "#22c55e";
        labelText = "reachable (" + model + ")";
        labelColor = "#22c55e";
      } else if (info.model_reachable === false) {
        dotColor = "#eab308";
        labelText = "auth/model failed (" + model + ")";
        labelColor = "#eab308";
      } else if (statusProbing || probesPending) {
        dotColor = "#94a3b8";
        labelText = "checking (" + model + ")";
        labelColor = "#94a3b8";
      } else {
        dotColor = "#eab308";
        labelText = "configured (" + model + ")";
        labelColor = "#eab308";
      }
      return React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "6px" } },
        React.createElement("span", { style: { fontSize: "12px", color: labelColor } }, labelText),
        React.createElement("span", { style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: dotColor, flexShrink: 0 } })
      );
    }

    function profileBadge(info, profileName) {
      if (savingProfile === profileName) {
        return React.createElement("span", { style: { fontSize: "12px", color: "#a78bfa" } }, "saving…");
      }
      if (probingProfile === profileName) {
        return React.createElement("span", { style: { fontSize: "12px", color: "#a78bfa" } }, "checking…");
      }
      if (savingProfile && savingProfile.indexOf("checking:" + profileName) === 0) {
        var parts = savingProfile.split("|");
        var checkingModel = parts[1] || (info && info.model) || "?";
        var checkingEffort = parts[2] || "";
        var label = "checking (" + checkingModel + (checkingEffort ? " · " + checkingEffort : "") + ")…";
        return React.createElement("span", { style: { fontSize: "12px", color: "#a78bfa" } }, label);
      }
      var inConfig = info && info.exists && info.has_model;
      var effort = profileEffortSuffix(info);
      var dotColor, labelText, labelColor;
      var modelLabel = (info && info.model) || "?";
      if (!inConfig) {
        dotColor = "#ef4444";
        labelText = info && info.exists ? "no model" : "not found";
        labelColor = "#f87171";
      } else if (info.model_reachable === true) {
        dotColor = "#22c55e";
        labelText = "reachable (" + modelLabel + effort + ")";
        labelColor = "#22c55e";
      } else if (info.model_reachable === false) {
        dotColor = "#eab308";
        var detail = (info.model_reachability_detail || "").trim();
        labelText = detail
          ? ("model unreachable — " + detail + " (" + modelLabel + effort + ")")
          : ("model unreachable (" + modelLabel + effort + ")");
        labelColor = "#eab308";
      } else if (statusProbing || probesPending) {
        dotColor = "#94a3b8";
        labelText = "checking (" + modelLabel + effort + ")";
        labelColor = "#94a3b8";
      } else {
        dotColor = "#eab308";
        labelText = "configured (" + modelLabel + effort + ")";
        labelColor = "#eab308";
      }
      return React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "6px" } },
        React.createElement("span", { style: { fontSize: "12px", color: labelColor } }, labelText),
        React.createElement("span", { style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: dotColor, flexShrink: 0 } })
      );
    }

    var statusInitialized = status && status.config_exists;
    var statusError = status && status.error;
    var statusLoading = status === null && loading;

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
        React.createElement(CardContent, { className: "flex items-start gap-3 py-4 max-[420px]:flex-col max-[420px]:gap-3" },
          React.createElement("div", { className: "flex min-w-0 flex-1 items-start gap-3" },
            React.createElement(StatusDot, { status: statusError ? "error" : statusInitialized ? "ok" : "warn" }),
            React.createElement("div", { className: "min-w-0 flex-1 space-y-1" },
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
            )
          ),
          React.createElement("div", { className: "flex shrink-0 flex-wrap items-center justify-end gap-2 max-[420px]:self-end" },
            React.createElement(Button, { onClick: runBootstrap, disabled: bootstrapping || pluginUpdating, size: "sm" },
              bootstrapping ? "Running…" : "Bootstrap"
            ),
            statusInitialized ? React.createElement(Button, { variant: "outline", size: "sm", onClick: runSave, disabled: bootstrapping || pluginUpdating },
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

      // ── Settings grid (left: Profiles → Cron → Project; right: Coding Agent → Walk Away → Governance) ──
      React.createElement("div", { className: "grid grid-cols-2 gap-4 items-stretch" },

          // Profiles (top left — pairs with Coding Agent row height)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Profiles")
            ),
            React.createElement(CardContent, { className: "flex flex-col flex-1 space-y-4" },
              (function () {
                var dispatch = (status && status.dispatch_profiles) || { orchestrator: "kanban-advanced-orchestrator", worker: "kanban-advanced-worker" };
                var rows = [
                  { key: "orchestrator", label: dispatch.orchestrator || "kanban-advanced-orchestrator" },
                  { key: "worker", label: dispatch.worker || "kanban-advanced-worker" }
                ];
                return rows.map(function (row) {
                  return React.createElement("div", {
                    key: row.label,
                    className: "flex items-center justify-between py-1.5 px-3 rounded-md border hover:bg-accent/5 cursor-pointer transition-colors",
                    onClick: function () { openModelPicker(row.label); }
                  },
                    React.createElement("span", { className: "text-sm" }, row.label),
                    profileBadge(status && status.profiles && status.profiles[row.label], row.label)
                  );
                });
              })(),
              React.createElement("p", { className: "text-[11px] text-muted-foreground mt-auto leading-snug" },
                "Click a profile to change model and reasoning effort."
              )
            )
          ),

          // Coding agent (top right)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Coding Agent")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Binary on PATH"),
                React.createElement("select", {
                  value: codingAgent,
                  onChange: function (e) { onCodingAgentBinaryChange(e.target.value); },
                  className: "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                },
                  codingAgentOptions.map(function (a) {
                    return React.createElement("option", { key: a.value, value: a.value }, a.label);
                  })
                ),
                (status && status.coding_agent_cli && status.coding_agent_cli.conflict_hint) ? React.createElement("p", { className: "text-[11px] text-amber-600 dark:text-amber-400 leading-snug" },
                  status.coding_agent_cli.conflict,
                  " — ",
                  status.coding_agent_cli.conflict_hint
                ) : null,
                React.createElement("p", { className: "text-[11px] text-muted-foreground" },
                  "Workers dispatch this binary. ",
                  React.createElement("a", { href: "https://github.com/thebizfixer/hermes-kanban-advanced-workflow/blob/main/docs/reference/coding-agents.md", target: "_blank", className: "underline" }, "Supported agents")
                )
              ),
              codingAgent === "__custom__" ? React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Custom binary name"),
                React.createElement(Input, {
                  value: customAgent,
                  onChange: function (e) { setCustomAgent(e.target.value); },
                  onBlur: function () {
                    if (codingAgent === "__custom__" && customAgent.trim()) {
                      resetCodingAgentModelForBinary(customAgent.trim());
                    }
                  },
                  placeholder: "e.g. my-agent",
                  className: "h-9"
                })
              ) : null,
              React.createElement("div", {
                className: cn(
                  "space-y-1.5 border-l-2 pl-3 ml-1",
                  codingAgentModelSelectionBlocked() ? "border-amber-500/40 opacity-60" : "border-muted"
                )
              },
                React.createElement(Label, { className: "text-xs" }, "Model for " + resolvedCodingBinary()),
                React.createElement("div", {
                  className: cn(
                    "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 text-sm shadow-sm transition-colors",
                    codingAgentModelSelectionBlocked()
                      ? "cursor-not-allowed opacity-70"
                      : "cursor-pointer hover:bg-accent/5"
                  ),
                  onClick: function () { if (!codingAgentModelSelectionBlocked()) openCodingAgentModelPicker(); }
                },
                  React.createElement("span", {
                    className: cn("font-mono truncate", !codingAgentModel ? "text-muted-foreground" : "")
                  }, codingAgentModelDisplay()),
                  codingAgentBadge(status && status.coding_agent_cli, codingAgentModel)
                ),
                codingAgentModelSelectionBlocked()
                  ? React.createElement("p", { className: "text-[11px] text-amber-600 dark:text-amber-400 leading-snug" },
                      codingAgentBinaryConflict(resolvedCodingBinary())
                        ? "Model selection is disabled while this binary name is contested. Choose an unambiguous command first."
                        : "Select a binary before choosing a model."
                    )
                  : React.createElement("p", { className: "text-[11px] text-muted-foreground" },
                      "Pick a model for this binary. Save or Bootstrap applies both settings together."
                    )
              )
            )
          ),

          // Cron (middle left)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Cron")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", {
                className: "flex items-center justify-between py-1.5 px-3 rounded-md border",
                onClick: function (e) { e.stopPropagation(); }
              },
                React.createElement("span", { className: "text-sm" }, "Lifecycle notify"),
                React.createElement("button", {
                  type: "button",
                  role: "switch",
                  "aria-checked": notifyLifecycle,
                  "aria-label": notifyLifecycle ? "Lifecycle cron notifications on" : "Lifecycle cron notifications off",
                  disabled: notifySaving || bootstrapping,
                  className: cn(
                    "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                    notifyLifecycle ? "bg-primary" : "bg-muted",
                    (notifySaving || bootstrapping) ? "opacity-60 cursor-not-allowed" : ""
                  ),
                  onClick: function () { setNotifyTouched(true); notifyTouchedRef.current = true; persistNotifyLifecycle(!notifyLifecycle); }
                },
                  React.createElement("span", {
                    className: cn(
                      "pointer-events-none block h-4 w-4 rounded-full bg-background shadow transition-transform",
                      notifyLifecycle ? "translate-x-4" : "translate-x-0"
                    )
                  })
                )
              ),
              React.createElement("p", { className: "text-[11px] text-muted-foreground leading-snug" },
                "Notifies at card start, running, and done after the gate completes, and when a running card re-blocks."
              )
            )
          ),

          // Walk Away (middle right — pairs with Cron row height)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Walk Away")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", {
                className: "flex items-center justify-between py-1.5 px-3 rounded-md border",
                onClick: function (e) { e.stopPropagation(); }
              },
                React.createElement("span", { className: "text-sm" }, "Toggle Off/On"),
                React.createElement("button", {
                  type: "button",
                  role: "switch",
                  "aria-checked": walkAwayMode,
                  "aria-label": walkAwayMode ? "Walk-away mode on" : "Walk-away mode off",
                  disabled: notifySaving || bootstrapping,
                  className: cn(
                    "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                    walkAwayMode ? "bg-primary" : "bg-muted",
                    (notifySaving || bootstrapping) ? "opacity-60 cursor-not-allowed" : ""
                  ),
                  onClick: function () { setWalkawayTouched(true); walkawayTouchedRef.current = true; persistWalkAwayMode(!walkAwayMode); }
                },
                  React.createElement("span", {
                    className: cn(
                      "pointer-events-none block h-4 w-4 rounded-full bg-background shadow transition-transform",
                      walkAwayMode ? "translate-x-4" : "translate-x-0"
                    )
                  })
                )
              ),
              React.createElement("p", { className: "text-[11px] text-muted-foreground leading-snug" },
                "When on, runs post-execution through completion notify after final audit without prompts; when off, waits for your approval."
              )
            )
          ),

          // Project (bottom left — pairs with Governance row height)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Project")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Working branch"),
                React.createElement(Input, { value: workingBranch, onChange: function (e) { setWorkingBranch(e.target.value); setWorkingBranchTouched(true); workingBranchTouchedRef.current = true; }, placeholder: "main", className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Integration branch for worktree commits. Defaults to your git checkout / origin default.")
              ),
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Trigger branch"),
                React.createElement(Input, { value: triggerBranch, onChange: function (e) { setTriggerBranch(e.target.value); setTriggerBranchTouched(true); triggerBranchTouchedRef.current = true; }, placeholder: "Optional", className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "The protected branch agents should NOT push to. Optional.")
              )
            )
          ),

          // Governance & Tuning (bottom right)
          React.createElement(Card, { className: "h-full min-h-0 flex flex-col" },
            React.createElement(CardHeader, null,
              React.createElement(CardTitle, { className: "text-sm font-semibold uppercase tracking-wide text-muted-foreground" }, "Governance & Tuning")
            ),
            React.createElement(CardContent, { className: "space-y-4" },
              React.createElement("div", { className: "space-y-1.5" },
                React.createElement(Label, { className: "text-xs" }, "Governance profile"),
                React.createElement("select", {
                  value: policyProfile,
                  onChange: function (e) { setPolicyProfile(e.target.value); setPolicyTouched(true); policyTouchedRef.current = true; },
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
                React.createElement(Input, { type: "number", value: maxTurns, onChange: function (e) { setMaxTurns(e.target.value); setMaxTurnsTouched(true); maxTurnsTouchedRef.current = true; }, min: 90, max: 500, className: "h-9" }),
                React.createElement("p", { className: "text-[11px] text-muted-foreground" }, "Recommended 180 for plan decomposition. Default is 90.")
              )
            )
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
              React.createElement("button", {
                onClick: function () { setEditingProfile(null); setSelectedModel(null); },
                className: "absolute right-2 top-2 w-7 h-7 flex items-center justify-center rounded-md hover:bg-accent/20 text-muted-foreground hover:text-foreground transition-colors z-10",
                "aria-label": "Close"
              }, "✕"),

              React.createElement("header", { className: "p-4 pb-3 border-b border-border" },
                React.createElement("h2", { className: "text-sm font-semibold tracking-wide" }, "Profile settings — " + editingProfile)
              ),

              React.createElement("div", { className: "overflow-y-auto max-h-64" },
                !modelOptions ? React.createElement("div", { className: "p-4 text-xs text-muted-foreground" }, "Loading…")
                : modelOptions.error ? React.createElement("div", { className: "p-4 text-xs text-red-400" }, "Could not load")
                : (modelOptions.providers || []).map(function (prov) {
                    var provId = prov.id || prov.slug || (typeof prov === "string" ? prov : "");
                    var provLabel = prov.name || provId || prov;
                    var provModels = prov.models || [];
                    if (!provModels.length) return null;
                    return React.createElement("div", { key: provId || provLabel },
                      React.createElement("div", { className: "px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide bg-muted/30" }, provLabel),
                      provModels.map(function (m) {
                        var modelId = typeof m === "string" ? m : m.id || m.name;
                        var modelLabel = typeof m === "string" ? m : m.name || m.id;
                        var profileInfo = status && status.profiles && status.profiles[editingProfile];
                        var isCurrent = profileInfo && profileInfo.model === modelId
                          && (!profileInfo.provider || profileInfo.provider === provId);
                        var isSel = selectedModel && selectedModel.model === modelId && selectedModel.provider === provId;
                        return React.createElement("div", {
                          key: modelId,
                          className: "flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer hover:bg-accent/10 transition-colors" + (isSel ? " bg-accent/10" : ""),
                          onClick: function () { setSelectedModel({ provider: provId, model: modelId }); }
                        },
                          React.createElement("span", { className: "w-3 h-3 shrink-0 flex items-center justify-center text-[10px]" }, isSel ? "✓" : ""),
                          React.createElement("span", { className: "flex-1 truncate font-mono" }, modelLabel),
                          isCurrent ? React.createElement("span", { className: "text-[10px] text-primary shrink-0" }, "current") : null
                        );
                      })
                    );
                  })
              ),

              React.createElement("div", { className: "border-t border-border px-4 py-3 space-y-2" },
                React.createElement(Label, { className: "text-xs", htmlFor: "profile-reasoning-effort" }, "Reasoning effort"),
                React.createElement("select", {
                  id: "profile-reasoning-effort",
                  className: "flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm",
                  value: pendingReasoningEffort,
                  "aria-label": "Reasoning effort for " + editingProfile,
                  "aria-describedby": "profile-reasoning-hint profile-reasoning-footnote",
                  onChange: function (e) { setPendingReasoningEffort(e.target.value); }
                },
                  REASONING_EFFORT_LEVELS.map(function (level) {
                    return React.createElement("option", { key: level, value: level }, level);
                  })
                ),
                React.createElement("p", {
                  id: "profile-reasoning-hint",
                  className: "text-[11px] text-muted-foreground"
                },
                  "Recommended for this role: ",
                  React.createElement("span", { className: "font-medium text-foreground" },
                    (status && status.profiles && status.profiles[editingProfile]
                      && status.profiles[editingProfile].recommended_reasoning_effort) || "medium"
                  ),
                  ". Applies to new sessions on this profile."
                ),
                React.createElement("p", {
                  id: "profile-reasoning-footnote",
                  className: "text-[11px] text-muted-foreground leading-snug"
                }, "Supported on providers with extended thinking (e.g. OpenRouter, Nous Portal). Other providers may ignore this setting.")
              ),

              React.createElement("footer", { className: "border-t border-border p-3 flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-[11px] text-muted-foreground truncate" },
                  (selectedModel ? selectedModel.model : ((status && status.profiles && status.profiles[editingProfile] && status.profiles[editingProfile].model) || "current model"))
                  + " · " + pendingReasoningEffort
                ),
                React.createElement("div", { className: "flex items-center gap-1.5 shrink-0" },
                  React.createElement(Button, { variant: "outline", size: "sm", onClick: function () { setEditingProfile(null); setSelectedModel(null); } }, "Cancel"),
                  React.createElement(Button, {
                    size: "sm",
                    disabled: !profileApplyEnabled() || !!savingProfile,
                    onClick: function () { applyProfileSettings(editingProfile); }
                  }, savingProfile ? "…" : "Apply")
                )
              )
            )
          ) : null,

      editingCodingAgentModel ? React.createElement("div", {
        className: "fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4",
        onClick: function (e) { if (e.target === e.currentTarget) setEditingCodingAgentModel(false); }
      },
        React.createElement("div", {
          className: "relative w-full max-w-md border border-border bg-card shadow-2xl flex flex-col overflow-hidden max-h-[80vh]",
          onClick: function (e) { e.stopPropagation(); }
        },
          React.createElement("header", { className: "border-b border-border px-4 py-3" },
            React.createElement("h3", { className: "text-sm font-semibold" }, "Coding agent model"),
            React.createElement("p", { className: "text-[11px] text-muted-foreground font-mono mt-0.5" }, resolvedCodingBinary())
          ),
          React.createElement("div", { className: "p-3 border-b border-border" },
            React.createElement(Input, {
              value: codingAgentModelQuery,
              onChange: function (e) { setCodingAgentModelQuery(e.target.value); },
              placeholder: "Filter models…",
              className: "h-8 text-xs"
            })
          ),
          React.createElement("div", { className: "flex-1 overflow-y-auto min-h-0" },
            !codingAgentModelOptions ? React.createElement("p", { className: "p-4 text-xs text-muted-foreground" }, "Loading models…")
              : codingAgentModelOptions.error ? React.createElement("p", { className: "p-4 text-xs text-red-400" }, "Could not load models")
              : codingAgentModelOptions.providers ? function () {
                  var q = (codingAgentModelQuery || "").toLowerCase();
                  var provs = (codingAgentModelOptions.providers || []).map(function (prov) {
                    var provId = prov.id || prov.slug || (typeof prov === "string" ? prov : "");
                    var provLabel = prov.name || provId || prov;
                    var provModels = (prov.models || []).filter(function (m) {
                      var modelId = typeof m === "string" ? m : m.id || m.name;
                      var modelLabel = typeof m === "string" ? m : m.name || m.id;
                      if (!q) return true;
                      return (modelId || "").toLowerCase().indexOf(q) >= 0 || (modelLabel || "").toLowerCase().indexOf(q) >= 0 || (provLabel || "").toLowerCase().indexOf(q) >= 0;
                    });
                    if (!provModels.length) return null;
                    return React.createElement("div", { key: provId || provLabel },
                      React.createElement("div", { className: "px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide bg-muted/30" }, provLabel),
                      provModels.map(function (m) {
                        var modelId = typeof m === "string" ? m : m.id || m.name;
                        var modelLabel = typeof m === "string" ? m : m.name || m.id;
                        var fullId = provId && modelId.indexOf("/") < 0 ? provId + "/" + modelId : modelId;
                        var isSel = pendingCodingAgentModel === fullId || pendingCodingAgentModel === modelId;
                        var isCurrent = codingAgentModel === fullId || codingAgentModel === modelId;
                        return React.createElement("div", {
                          key: fullId,
                          className: "flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer hover:bg-accent/10 transition-colors" + (isSel ? " bg-accent/10" : ""),
                          onClick: function () { setPendingCodingAgentModel(fullId); }
                        },
                          React.createElement("span", { className: "w-3 h-3 shrink-0 flex items-center justify-center text-[10px]" }, isSel ? "✓" : ""),
                          React.createElement("span", { className: "flex-1 truncate font-mono" }, modelLabel),
                          isCurrent ? React.createElement("span", { className: "text-[10px] text-primary shrink-0" }, "current") : null
                        );
                      })
                    );
                  }).filter(Boolean);
                  // Prepend the "Auto" option for hermes
                  var autoEntry = React.createElement("div", {
                    key: "__auto__",
                    className: "flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer hover:bg-accent/10 transition-colors" + (pendingCodingAgentModel === "auto" ? " bg-accent/10" : ""),
                    onClick: function () { setPendingCodingAgentModel("auto"); }
                  },
                    React.createElement("span", { className: "w-3 h-3 shrink-0 flex items-center justify-center text-[10px]" }, pendingCodingAgentModel === "auto" ? "✓" : ""),
                    React.createElement("span", { className: "flex-1 truncate font-mono" }, codingAgentModelDisplay())
                  );
                  return [autoEntry].concat(provs);
                }()
              : (codingAgentModelOptions.models || []).filter(function (m) {
                  var q = (codingAgentModelQuery || "").toLowerCase();
                  if (!q) return true;
                  return (m.id || "").toLowerCase().indexOf(q) >= 0 || (m.label || "").toLowerCase().indexOf(q) >= 0;
                }).map(function (m) {
                  var isSel = pendingCodingAgentModel === m.id;
                  var isCurrent = codingAgentModel === m.id;
                  return React.createElement("div", {
                    key: m.id,
                    className: "flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer hover:bg-accent/10 transition-colors" + (isSel ? " bg-accent/10" : ""),
                    onClick: function () { setPendingCodingAgentModel(m.id); }
                  },
                    React.createElement("span", { className: "w-3 h-3 shrink-0 flex items-center justify-center text-[10px]" }, isSel ? "✓" : ""),
                    React.createElement("span", { className: "flex-1 truncate font-mono" }, m.label || m.id),
                    isCurrent ? React.createElement("span", { className: "text-[10px] text-primary shrink-0" }, "current") : null
                  );
                })
          ),
          React.createElement("footer", { className: "border-t border-border p-3 flex items-center justify-between gap-2" },
            React.createElement("span", { className: "text-[11px] text-muted-foreground font-mono truncate" }, pendingCodingAgentModel || "(none selected)"),
            React.createElement("div", { className: "flex items-center gap-1.5" },
              React.createElement(Button, { variant: "outline", size: "sm", onClick: function () { setEditingCodingAgentModel(false); } }, "Cancel"),
              React.createElement(Button, { size: "sm", disabled: !pendingCodingAgentModel, onClick: applyCodingAgentModelChoice }, "Select")
            )
          )
        )
      ) : null,

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
