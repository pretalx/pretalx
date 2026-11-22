// SPDX-FileCopyrightText: 2018-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const globalData = document.getElementById("global-data")
const dataMapping = JSON.parse(globalData.dataset.mapping)
let searchUrl = globalData.dataset.url

const durationFormats = JSON.parse(globalData.dataset.durationFormats)
const formatDuration = (minutes) => {
    if (minutes < 60) return durationFormats.minutes.replace("{n}", minutes)
    const hours = (minutes / 60).toLocaleString(document.documentElement.lang, {
        maximumFractionDigits: 1,
    })
    return durationFormats.hours.replace("{n}", hours)
}

const drawTimeline = (includePending = false) => {
    const dataElements = [
        "submission-timeline-data",
        includePending ? "talk-pending-timeline-data" : "talk-timeline-data",
        "total-submission-timeline-data",
    ]
        .map((id) => document.getElementById(id))
        .filter((element) => element?.dataset.timeline)
    const element = document.getElementById("timeline")
    if (!element || !dataElements.length) return
    const deadlines = JSON.parse(globalData.dataset.annotations).deadlines.map(
        (element) => ({
            x: new Date(element[0]).getTime(),
            borderColor: "#ff4560",
            strokeDashArray: 0,
            label: {
                style: {
                    borderColor: "#ff4560",
                    background: "#ff4560",
                    color: "#fff",
                    fontSize: "14px",
                    padding: { top: 5 },
                },
                text: element[1],
            },
        }),
    )
    const options = {
        series: dataElements.map((element) => ({
            name: element.dataset.label,
            data: JSON.parse(element.dataset.timeline).map((element) => ({
                x: new Date(element.x),
                y: element.y,
            })),
        })),
        xaxis: {
            type: "datetime",
            tooltip: { enabled: false },
        },
        annotations: {
            xaxis: deadlines,
        },
        chart: {
            redrawOnParentResize: true,
            height: 250,
            type: "area",
            toolbar: {
                tools: {
                    selection: false,
                    zoom: false,
                    zoomin: false,
                    zoomout: false,
                    pan: false,
                    reset: false,
                },
            },
        },
        colors: ["#3aa57c", "#4697c9", "#cccccc"],
        fill: {
            type: ["gradient", "gradient", "gradient"],
        },
        dataLabels: {
            enabled: false,
        },
        legend: {
            formatter: (val, _opts) => {
                if (val.length > 15) val = `${val.slice(0, 15)}…`
                return val
            },
            position: "top",
        },
        responsive: [
            {
                breakpoint: 480,
                options: {
                    chart: {
                        width: 300,
                    },
                    legend: {
                        position: "bottom",
                    },
                },
            },
        ],
        tooltip: {
            enabled: true,
            shared: true,
            x: { show: true },
            marker: { show: true },
            onDatasetHover: { highlightDataSeries: true },
        },
    }
    const chart = new ApexCharts(element, options)
    chart.render()
    return chart
}

const getPieData = (id) => {
    const element = document.getElementById(id)
    if (!element?.dataset.states) return
    const data = JSON.parse(element.dataset.states)
    return {
        series: data.map((e) => e.value),
        labels: data.map((e) => e.label),
        minutes: data.map((e) => e.minutes),
    }
}

const drawPieChart = (data, scope, type) => {
    const id = `${scope}-${type}`
    const element = document.getElementById(id)
    const typeMapping = {
        track: "track",
        "track-duration": "track",
        type: "submission_type",
        state: "state",
    }
    const valueDisplay = (index) => {
        if (type === "duration") {
            return `${data.series[index]} (${formatDuration(data.minutes[index])})`
        }
        if (type === "track-duration") return formatDuration(data.series[index])
        return data.series[index]
    }
    const options = {
        series: data.series,
        labels: data.labels,
        chart: {
            width: element.clientWidth - 50,
            redrawOnParentResize: true,
            type: "donut",
            events: {},
        },
        dataLabels: {
            enabled: false,
        },
        legend: {
            formatter: (val, opts) => {
                if (val.length > 15) val = `${val.slice(0, 15)}…`
                return `${escapeHtml(val)} - ${valueDisplay(opts.seriesIndex)}`
            },
        },
        responsive: [
            {
                breakpoint: 480,
                options: {
                    chart: {
                        width: 300,
                    },
                    legend: {
                        position: "bottom",
                    },
                },
            },
        ],
        plotOptions: {
            pie: {
                donut: {
                    labels: {
                        show: true,
                        name: {
                            formatter: (val) => {
                                const details = val.indexOf("(") // Truncate duration display in centre of donut chart
                                if (details > -1) val = val.substring(0, details)
                                if (val.length < 16) return val
                                return `${val.slice(0, 15)}…`
                            },
                        },
                    },
                },
            },
        },
        tooltip: {
            enabled: false,
        },
    }
    // Add click handlers for filterable chart types (track, track-duration, type, state).
    // Duration charts are non-clickable because they have no corresponding filter.
    const filterType = type === "track-duration" ? "track" : type
    if (typeMapping[filterType]) {
        options.chart.events = {
            dataPointSelection: (_event, _chartContext, config) => {
                const label = config.w.config.labels[config.dataPointIndex]
                const searchValue = dataMapping[filterType][label]
                searchUrl += `&${typeMapping[filterType]}=${searchValue}`
                window.location.href = searchUrl
            },
            dataPointMouseEnter: () => {
                element.style.cursor = "pointer"
            },
            dataPointMouseLeave: () => {
                element.style.cursor = "inherit"
            },
        }
    }
    // Add donut centre "Total" label for duration-based charts.
    // Shows total count + time for duration charts, or total time for track-duration.
    if (type === "duration" || type === "track-duration") {
        const sum = (values) => values.reduce((a, b) => a + b, 0)
        options.plotOptions.pie.donut.labels.total = {
            show: true,
            label: durationFormats.total,
            formatter: () =>
                type === "duration"
                    ? `${sum(data.series)} (${formatDuration(sum(data.minutes))})`
                    : formatDuration(sum(data.series)),
        }
    }
    // Format the centre hover value for track-duration to show time instead of raw minutes
    if (type === "track-duration") {
        options.plotOptions.pie.donut.labels.value = {
            formatter: (val) => formatDuration(Number(val)),
        }
    }

    const chart = new ApexCharts(element, options)
    chart.render()
    return chart
}

const chartTypes = ["state", "duration"]
if (dataMapping.type && Object.keys(dataMapping.type).length > 1)
    chartTypes.push("type")
if (dataMapping.track) chartTypes.push("track", "track-duration")
const getChartData = (scope) =>
    chartTypes.reduce((result, item) => {
        const data = getPieData(`${scope}-${item}-data`)
        if (data) result[item] = data
        return result
    }, {})
const submissionChartData = getChartData("submission")
const talkChartData = getChartData("talk")
const talkPendingChartData = getChartData("talk-pending")
const includePendingGroup = document.getElementById("include-pending-group")
const includePendingCheckbox = document.getElementById("include-pending")
const includePending = () => includePendingCheckbox?.checked
/* generate timeline data. delay to draw the correct size immediately */
let timelineChart = null
setTimeout(() => {
    timelineChart = drawTimeline()
}, 10)

let charts = []

const showCardHeaders = (element, showTalks) => {
    const card = element.closest(".card")
    if (!card) return
    const submissionHeader = card.querySelector(".card-header.submissions")
    const talkHeader = card.querySelector(".card-header.talks")
    if (submissionHeader) submissionHeader.classList.toggle("d-none", showTalks)
    if (talkHeader) talkHeader.classList.toggle("d-none", !showTalks)
}

const drawPieCharts = (showTalks) => {
    charts.forEach((chart) => chart.destroy())
    charts = []
    includePendingGroup?.classList.toggle("d-none", !showTalks)
    let chartData = submissionChartData
    if (showTalks) {
        chartData = includePending() ? talkPendingChartData : talkChartData
    }
    for (const key of chartTypes) {
        const submissionElement = document.getElementById(`submission-${key}`)
        const talkElement = document.getElementById(`talk-${key}`)
        if (!submissionElement || !talkElement) continue
        const data = chartData[key]
        const card = submissionElement.closest(".card")
        if (card) card.classList.toggle("d-none", !data)
        submissionElement.classList.toggle("d-none", showTalks)
        talkElement.classList.toggle("d-none", !showTalks)
        showCardHeaders(submissionElement, showTalks)
        if (data)
            charts.push(drawPieChart(data, showTalks ? "talk" : "submission", key))
    }
}

const showTalks = () =>
    document.querySelector("input[name='stats-toggle']:checked").value === "talks"
drawPieCharts(showTalks())
document.querySelectorAll("input[name='stats-toggle']").forEach((input) => {
    input.addEventListener("change", () => drawPieCharts(showTalks()))
})
includePendingCheckbox?.addEventListener("change", () => {
    drawPieCharts(showTalks())
    if (timelineChart) {
        timelineChart.destroy()
        timelineChart = drawTimeline(includePendingCheckbox.checked)
    }
})
