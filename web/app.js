(() => {
  "use strict";

  const fmtInt = new Intl.NumberFormat("en-US");
  const fmtMoney = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const fmtPct = (value) => `${(value * 100).toFixed(2)}%`;

  const state = {
    all: [],
    flagged: [],
    daily: [],
    flagSummary: [],
    metrics: null,
    filtered: [],
    charts: {},
    page: 1,
    pageSize: 50,
    sortKey: "Risk_Score",
    sortDir: "desc",
  };

  const $ = (id) => document.getElementById(id);

  const RULE_LABELS = [
    ["Flag_High_Amount", "High amount"],
    ["Flag_High_Frequency", "High frequency"],
    ["Flag_Location", "Unusual city"],
    ["Flag_Timing", "Night timing"],
    ["Flag_Failures", "Repeated failures"],
  ];

  function setText(id, text) {
    const node = $(id);
    if (node) node.textContent = text;
  }

  function parseCsv(text) {
    return new Promise((resolve, reject) => {
      Papa.parse(text, {
        header: true,
        skipEmptyLines: "greedy",
        dynamicTyping: true,
        complete: (result) => {
          const fatal = (result.errors || []).filter((error) => error.type === "Delimiter");
          if (fatal.length) {
            reject(new Error(fatal[0].message));
            return;
          }
          resolve(result.data);
        },
        error: reject,
      });
    });
  }

  async function loadCsv(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load ${path} (HTTP ${response.status}).`);
    }
    return parseCsv(await response.text());
  }

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load ${path} (HTTP ${response.status}).`);
    }
    return response.json();
  }

  function showError(message) {
    const banner = document.createElement("div");
    banner.className = "callout callout-error";
    banner.setAttribute("role", "alert");
    banner.textContent = message;
    const main = $("main");
    main.prepend(banner);
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function riskSortValue(level) {
    return { None: 0, Low: 1, Medium: 2, High: 3 }[level] ?? -1;
  }

  function sortValue(row, key) {
    if (key === "Risk_Level") return riskSortValue(row.Risk_Level);
    return row[key];
  }

  function compareValues(a, b) {
    if (a === b) return 0;
    if (a === null || a === undefined || a === "") return 1;
    if (b === null || b === undefined || b === "") return -1;
    if (typeof a === "number" && typeof b === "number") return a - b;
    const aText = String(a).trim();
    const bText = String(b).trim();
    const aNumber = Number(aText);
    const bNumber = Number(bText);
    if (
      aText !== "" &&
      bText !== "" &&
      !Number.isNaN(aNumber) &&
      !Number.isNaN(bNumber)
    ) {
      return aNumber - bNumber;
    }
    return aText.localeCompare(bText);
  }

  function initCharts() {
    if (!window.Chart) {
      throw new Error("Chart.js did not load. Check web/vendor/chart.umd.min.js.");
    }

    Chart.defaults.font.family =
      'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
    Chart.defaults.color = "#52627a";
    Chart.defaults.borderColor = "#e2e8f0";

    const centerText = {
      id: "centerText",
      afterDraw(chart) {
        if (chart.config.type !== "doughnut") return;
        const { ctx, chartArea } = chart;
        if (!chartArea) return;
        const total = chart.data.datasets[0].data.reduce((sum, value) => sum + value, 0);
        const x = (chartArea.left + chartArea.right) / 2;
        const y = (chartArea.top + chartArea.bottom) / 2;
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#0f172a";
        ctx.font = '700 28px system-ui, -apple-system, "Segoe UI", sans-serif';
        ctx.fillText(fmtInt.format(total), x, y - 8);
        ctx.fillStyle = "#52627a";
        ctx.font = '600 11px system-ui, -apple-system, "Segoe UI", sans-serif';
        ctx.fillText("FLAGGED", x, y + 18);
        ctx.restore();
      },
    };

    const barValueLabels = {
      id: "barValueLabels",
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        if (!meta || meta.type !== "bar") return;
        if (chart.canvas.id === "type-recall-chart") return;
        const { ctx } = chart;
        const horizontal = chart.options.indexAxis === "y";
        ctx.save();
        ctx.fillStyle = "#334155";
        ctx.font = '600 11px system-ui, -apple-system, "Segoe UI", sans-serif';
        meta.data.forEach((bar, index) => {
          const value = chart.data.datasets[0].data[index];
          if (horizontal) {
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillText(fmtInt.format(value), bar.x + 6, bar.y);
          } else {
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(fmtInt.format(value), bar.x, bar.y - 4);
          }
        });
        ctx.restore();
      },
    };

    const percentBarLabels = {
      id: "percentBarLabels",
      afterDatasetsDraw(chart) {
        if (chart.canvas.id !== "type-recall-chart") return;
        const meta = chart.getDatasetMeta(0);
        if (!meta || meta.type !== "bar") return;
        const { ctx } = chart;
        ctx.save();
        ctx.fillStyle = "#334155";
        ctx.font = '600 11px system-ui, -apple-system, "Segoe UI", sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        meta.data.forEach((bar, index) => {
          const value = chart.data.datasets[0].data[index];
          ctx.fillText(`${value.toFixed(1)}%`, bar.x + 6, bar.y);
        });
        ctx.restore();
      },
    };

    Chart.register(centerText, barValueLabels, percentBarLabels);

    const daily = state.daily
      .slice()
      .sort((a, b) => String(a.Date).localeCompare(String(b.Date)));

    state.charts.daily = new Chart($("daily-chart"), {
      type: "line",
      data: {
        labels: daily.map((row) => row.Date),
        datasets: [
          {
            label: "Total transactions",
            data: daily.map((row) => Number(row.Total_Transactions)),
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(29, 78, 216, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.28,
            fill: true,
            yAxisID: "y",
          },
          {
            label: "Flagged transactions",
            data: daily.map((row) => Number(row.Flagged_Count)),
            borderColor: "#dc2626",
            backgroundColor: "rgba(220, 38, 38, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.28,
            fill: false,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => `${context.dataset.label}: ${fmtInt.format(context.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 10, maxRotation: 0, autoSkip: true },
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#eef2f7" },
            title: { display: true, text: "Total transactions", color: "#1d4ed8" },
          },
          y1: {
            beginAtZero: true,
            position: "right",
            ticks: { precision: 0 },
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Flagged", color: "#dc2626" },
          },
        },
      },
    });

    const riskOrder = ["Low", "Medium", "High"];
    const riskCounts = riskOrder.map(
      (level) => state.flagged.filter((row) => row.Risk_Level === level).length
    );

    state.charts.risk = new Chart($("risk-chart"), {
      type: "doughnut",
      data: {
        labels: riskOrder,
        datasets: [
          {
            data: riskCounts,
            backgroundColor: ["#0ea5e9", "#f59e0b", "#dc2626"],
            borderColor: "#ffffff",
            borderWidth: 3,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, padding: 16, usePointStyle: true },
          },
          tooltip: {
            callbacks: {
              label: (context) => `${context.label}: ${fmtInt.format(context.parsed)} rows`,
            },
          },
        },
      },
    });

    const summary = state.flagSummary
      .slice()
      .sort((a, b) => Number(b.Count) - Number(a.Count));

    state.charts.rules = new Chart($("rule-chart"), {
      type: "bar",
      data: {
        labels: summary.map((row) => row.Flag_Type),
        datasets: [
          {
            label: "Rows where the rule fired",
            data: summary.map((row) => Number(row.Count)),
            backgroundColor: "#0f766e",
            borderRadius: 5,
            maxBarThickness: 26,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 48 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => {
                const row = summary[context.dataIndex];
                return `${fmtInt.format(row.Count)} rows, INR ${fmtMoney.format(row.Total_Value)}`;
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#eef2f7" },
          },
          y: { grid: { display: false } },
        },
      },
    });

    const scoreCounts = new Map();
    state.flagged.forEach((row) => {
      const score = Number(row.Risk_Score);
      scoreCounts.set(score, (scoreCounts.get(score) || 0) + 1);
    });
    const scoreRows = [...scoreCounts.entries()].sort((a, b) => a[0] - b[0]);
    const scoreColors = scoreRows.map(([score]) =>
      score >= 60 ? "#dc2626" : score >= 30 ? "#f59e0b" : "#0ea5e9"
    );

    state.charts.score = new Chart($("score-chart"), {
      type: "bar",
      data: {
        labels: scoreRows.map(([score]) => score),
        datasets: [
          {
            label: "Flagged rows",
            data: scoreRows.map(([, count]) => count),
            backgroundColor: scoreColors,
            borderRadius: 4,
            maxBarThickness: 26,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => `Risk score ${items[0].label}`,
              label: (context) => `${fmtInt.format(context.parsed.y)} rows`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            title: { display: true, text: "Risk score" },
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#eef2f7" },
          },
        },
      },
    });

    const typeRows = state.metrics.base_type_rows
      .slice()
      .sort((a, b) => b.Recall - a.Recall);
    const typeColors = typeRows.map((row) =>
      row.Recall >= 1
        ? "#15803d"
        : row.Recall >= 0.9
          ? "#2563eb"
          : row.Recall >= 0.8
            ? "#f59e0b"
            : "#dc2626"
    );

    state.charts.typeRecall = new Chart($("type-recall-chart"), {
      type: "bar",
      data: {
        labels: typeRows.map((row) => row.Type),
        datasets: [
          {
            label: "Recall",
            data: typeRows.map((row) => row.Recall * 100),
            backgroundColor: typeColors,
            borderRadius: 4,
            maxBarThickness: 20,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 62 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => {
                const row = typeRows[context.dataIndex];
                return `${fmtInt.format(row.Detected_Rows)} of ${fmtInt.format(
                  row.Injected_Rows
                )} detected (${fmtPct(row.Recall)})`;
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            max: 100,
            ticks: { callback: (value) => `${value}%` },
            grid: { color: "#eef2f7" },
          },
          y: { grid: { display: false } },
        },
      },
    });

    const locations = new Map();
    state.all.forEach((row) => {
      const city = row.Location || "Unknown";
      locations.set(city, (locations.get(city) || 0) + 1);
    });
    const locationRows = [...locations.entries()].sort((a, b) => b[1] - a[1]);

    state.charts.locations = new Chart($("location-chart"), {
      type: "bar",
      data: {
        labels: locationRows.map(([city]) => city),
        datasets: [
          {
            label: "Transactions",
            data: locationRows.map(([, count]) => count),
            backgroundColor: locationRows.map(([city]) =>
              city === "Unknown" ? "#94a3b8" : "#2563eb"
            ),
            borderRadius: 5,
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 52 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => `${fmtInt.format(context.parsed.x)} transactions`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#eef2f7" },
          },
          y: { grid: { display: false } },
        },
      },
    });
  }

  function initKpis() {
    const total = state.all.length;
    const flagged = state.flagged.length;
    const totalValue = state.all.reduce((sum, row) => sum + Number(row.Amount || 0), 0);
    const flaggedValue = state.flagged.reduce((sum, row) => sum + Number(row.Amount || 0), 0);

    setText("kpi-total", fmtInt.format(total));
    setText("kpi-flagged", fmtInt.format(flagged));
    setText("kpi-flagged-pct", fmtPct(total ? flagged / total : 0));
    setText("kpi-total-value", `INR ${fmtMoney.format(totalValue)}`);
    setText("kpi-flagged-value", `INR ${fmtMoney.format(flaggedValue)}`);
    setText(
      "kpi-flagged-note",
      `${fmtInt.format(flagged)} rows, ${fmtPct(total ? flagged / total : 0)} of the file`
    );
    setText(
      "kpi-flagged-value-note",
      `${fmtPct(totalValue ? flaggedValue / totalValue : 0)} of total value`
    );

    setText("hero-total", fmtInt.format(total));
    setText("hero-flagged", fmtInt.format(flagged));
    setText("hero-precision", fmtPct(state.metrics.precision));
    setText("hero-recall", fmtPct(state.metrics.recall));

    const highOnly = state.metrics.fp_combinations.find(
      (row) => row.Combination === "High Amount"
    );
    setText("finding-fp-value", highOnly ? fmtInt.format(highOnly.Count) : "0");
    setText(
      "finding-fp-note",
      highOnly
        ? `of ${fmtInt.format(state.metrics.false_positive)} false positives were High Amount only`
        : "No High Amount-only false positives"
    );

    const perfect = state.metrics.base_type_rows
      .filter((row) => row.Recall === 1)
      .map((row) => row.Type);
    setText("finding-perfect-value", perfect.length ? "100%" : "None");
    setText(
      "finding-perfect-note",
      perfect.length
        ? `${perfect.join(" and ")} found every planted row`
        : "No planted type reached 100% recall"
    );

    const baseRows = state.metrics.base_type_rows;
    const weakest = baseRows.length
      ? baseRows.reduce((min, row) => (row.Recall < min.Recall ? row : min), baseRows[0])
      : null;
    if (weakest) {
      setText("finding-weak-value", fmtPct(weakest.Recall));
      setText(
        "finding-weak-note",
        `${weakest.Type}: ${fmtInt.format(weakest.Detected_Rows)} of ${fmtInt.format(
          weakest.Injected_Rows
        )} found`
      );
    }

    const highRisk = state.flagged.filter((row) => row.Risk_Level === "High").length;
    const mediumRisk = state.flagged.filter((row) => row.Risk_Level === "Medium").length;
    const lowRisk = state.flagged.filter((row) => row.Risk_Level === "Low").length;
    setText("finding-risk-value", `High ${fmtInt.format(highRisk)}`);
    setText(
      "finding-risk-note",
      `${fmtInt.format(mediumRisk)} Medium, ${fmtInt.format(
        lowRisk
      )} Low; average score ${state.metrics.avg_flagged_score.toFixed(2)}`
    );

    setText(
      "risk-note",
      `High: ${fmtInt.format(highRisk)} · ` +
        `Medium: ${fmtInt.format(mediumRisk)} · ` +
        `Low: ${fmtInt.format(lowRisk)}`
    );
  }

  function initValidation() {
    const m = state.metrics;
    setText("metric-precision", fmtPct(m.precision));
    setText("metric-recall", fmtPct(m.recall));
    setText("metric-f1", fmtPct(m.f1));
    setText("metric-flagged", fmtInt.format(m.flagged_rows));

    setText("cell-tp", fmtInt.format(m.true_positive));
    setText("cell-fp", fmtInt.format(m.false_positive));
    setText("cell-fn", fmtInt.format(m.false_negative));
    setText("cell-tn", fmtInt.format(m.true_negative));

    const typeBody = $("type-recall-body");
    typeBody.replaceChildren();
    m.base_type_rows.forEach((row) => {
      const tr = document.createElement("tr");
      const values = [
        row.Type,
        fmtInt.format(row.Detected_Rows),
        fmtInt.format(row.Injected_Rows),
        fmtPct(row.Recall),
      ];
      values.forEach((value, index) => {
        const td = document.createElement("td");
        td.textContent = value;
        if (index > 0) td.className = "num";
        tr.appendChild(td);
      });
      typeBody.appendChild(tr);
    });

    const comboBody = $("fp-combo-body");
    comboBody.replaceChildren();
    m.fp_combinations.forEach((row) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = row.Combination;
      const count = document.createElement("td");
      count.className = "num";
      count.textContent = fmtInt.format(row.Count);
      tr.append(name, count);
      comboBody.appendChild(tr);
    });

    const ruleBody = $("fp-rule-body");
    ruleBody.replaceChildren();
    Object.entries(m.fp_by_rule).forEach(([rule, count]) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = rule;
      const value = document.createElement("td");
      value.className = "num";
      value.textContent = fmtInt.format(count);
      tr.append(name, value);
      ruleBody.appendChild(tr);
    });
  }

  function riskRank(level) {
    return { High: 0, Medium: 1, Low: 2 }[level] ?? 3;
  }

  function initFilters() {
    const riskSelect = $("filter-risk");
    const locationSelect = $("filter-location");
    const typeSelect = $("filter-type");

    const risks = [...new Set(state.flagged.map((row) => row.Risk_Level))]
      .filter(Boolean)
      .sort((a, b) => riskRank(a) - riskRank(b));
    risks.forEach((risk) => {
      const option = document.createElement("option");
      option.value = risk;
      option.textContent = risk;
      riskSelect.appendChild(option);
    });

    const locations = [...new Set(state.flagged.map((row) => row.Location))]
      .filter(Boolean)
      .sort((a, b) => String(a).localeCompare(String(b)));
    locations.forEach((location) => {
      const option = document.createElement("option");
      option.value = location;
      option.textContent = location;
      locationSelect.appendChild(option);
    });

    const types = [...new Set(state.flagged.map((row) => row.Transaction_Type))]
      .filter(Boolean)
      .sort((a, b) => String(a).localeCompare(String(b)));
    types.forEach((type) => {
      const option = document.createElement("option");
      option.value = type;
      option.textContent = type;
      typeSelect.appendChild(option);
    });

    const form = $("filters");
    form.addEventListener("input", applyFilters);
    form.addEventListener("change", applyFilters);
    form.addEventListener("reset", () => {
      window.setTimeout(applyFilters, 0);
    });
  }

  function initTableControls() {
    document.querySelectorAll("th.sortable").forEach((th) => {
      th.tabIndex = 0;
      const activate = () => sortBy(th.dataset.sort);
      th.addEventListener("click", activate);
      th.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });

    $("prev-page").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        renderTable();
      }
    });

    $("next-page").addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
      if (state.page < totalPages) {
        state.page += 1;
        renderTable();
      }
    });

    $("page-size").addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value);
      state.page = 1;
      renderTable();
    });

    $("download-csv").addEventListener("click", downloadCsv);
  }

  function sortBy(key) {
    if (!key) return;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir =
        key === "Risk_Score" || key === "Amount" || key === "Risk_Level" ? "desc" : "asc";
    }
    applyFilters();
  }

  function sortFiltered() {
    state.filtered.sort((a, b) => {
      const result = compareValues(
        sortValue(a, state.sortKey),
        sortValue(b, state.sortKey)
      );
      return state.sortDir === "asc" ? result : -result;
    });
  }

  function applyFilters() {
    const text = $("filter-text").value.trim().toLowerCase();
    const risk = $("filter-risk").value;
    const location = $("filter-location").value;
    const type = $("filter-type").value;

    state.filtered = state.flagged.filter((row) => {
      if (risk && row.Risk_Level !== risk) return false;
      if (location && row.Location !== location) return false;
      if (type && row.Transaction_Type !== type) return false;
      if (text) {
        const haystack = [
          row.Transaction_ID,
          row.Customer_ID,
          row.Location,
          row.Transaction_Type,
          row.Merchant_Category,
          row.Flag_Reasons,
          row.Risk_Level,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(text)) return false;
      }
      return true;
    });

    sortFiltered();
    state.page = 1;
    renderTable();
  }

  function updateSortHeaders() {
    document.querySelectorAll("th.sortable").forEach((th) => {
      if (th.dataset.sort === state.sortKey) {
        const ascending = state.sortDir === "asc";
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        th.dataset.arrow = ascending ? "▲" : "▼";
      } else {
        th.setAttribute("aria-sort", "none");
        th.dataset.arrow = "↕";
      }
    });
  }

  function renderTable() {
    const body = $("flagged-body");
    const totalRows = state.filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalRows / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const start = totalRows ? (state.page - 1) * state.pageSize : 0;
    const end = Math.min(start + state.pageSize, totalRows);
    const pageRows = state.filtered.slice(start, end);
    const fragment = document.createDocumentFragment();

    pageRows.forEach((row) => {
      const tr = document.createElement("tr");

      const values = [
        ["Transaction", row.Transaction_ID],
        ["Time", formatTime(row.Transaction_Time)],
        ["Customer", row.Customer_ID],
        ["Amount", `INR ${fmtMoney.format(Number(row.Amount || 0))}`],
        ["Location", row.Location],
        ["Type", row.Transaction_Type],
        ["Score", row.Risk_Score],
      ];

      values.forEach(([label, value], index) => {
        const td = document.createElement("td");
        td.textContent = value ?? "";
        if (index === 1) td.classList.add("time-cell");
        if (index === 3 || index === 6) td.classList.add("num");
        if (index === 6) td.classList.add("score");
        tr.appendChild(td);
      });

      const riskCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `risk risk-${String(row.Risk_Level || "").toLowerCase()}`;
      badge.textContent = row.Risk_Level || "";
      riskCell.appendChild(badge);
      tr.appendChild(riskCell);

      const reasonCell = document.createElement("td");
      reasonCell.className = "reason";
      const fired = RULE_LABELS.filter(([column]) => Number(row[column]) === 1);
      if (fired.length) {
        const list = document.createElement("span");
        list.className = "reason-chips";
        fired.forEach(([, label]) => {
          const chip = document.createElement("span");
          chip.className = "chip";
          chip.textContent = label;
          list.appendChild(chip);
        });
        reasonCell.appendChild(list);
        reasonCell.title = row.Flag_Reasons || fired.map(([, label]) => label).join("; ");
        reasonCell.setAttribute("aria-label", row.Flag_Reasons || "");
      } else {
        reasonCell.textContent = row.Flag_Reasons || "";
      }
      tr.appendChild(reasonCell);

      fragment.appendChild(tr);
    });

    body.replaceChildren(fragment);
    if (!totalRows) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 9;
      td.textContent = "No flagged rows match these filters.";
      tr.appendChild(td);
      body.appendChild(tr);
    }

    setText(
      "table-count",
      totalRows
        ? `Showing ${fmtInt.format(start + 1)}-${fmtInt.format(end)} of ${fmtInt.format(
            totalRows
          )} flagged rows`
        : "No flagged rows match these filters"
    );
    setText("page-info", `Page ${state.page} of ${totalPages}`);
    $("prev-page").disabled = state.page <= 1 || totalRows === 0;
    $("next-page").disabled = state.page >= totalPages || totalRows === 0;
    updateSortHeaders();
  }

  function csvEscape(value) {
    const text = value === null || value === undefined ? "" : String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function downloadCsv() {
    if (!state.filtered.length) return;
    const columns = Object.keys(state.flagged[0]);
    const lines = [columns.join(",")];
    state.filtered.forEach((row) => {
      lines.push(columns.map((column) => csvEscape(row[column])).join(","));
    });
    const blob = new Blob([`\ufeff${lines.join("\r\n")}`], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "flagged_transactions_filtered.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function main() {
    try {
      const [all, flagged, daily, flagSummary, metrics] = await Promise.all([
        loadCsv("data/all_transactions_scored.csv"),
        loadCsv("data/flagged_transactions.csv"),
        loadCsv("data/daily_summary.csv"),
        loadCsv("data/flag_summary.csv"),
        loadJson("data/metrics.json"),
      ]);

      state.all = all;
      state.flagged = flagged;
      state.daily = daily;
      state.flagSummary = flagSummary;
      state.metrics = metrics;
      state.filtered = flagged.slice();

      initKpis();
      initValidation();
      initCharts();
      initFilters();
      initTableControls();
      applyFilters();
    } catch (error) {
      console.error(error);
      showError(`The dashboard data could not be loaded. ${error.message}`);
    }
  }

  main();
})();
