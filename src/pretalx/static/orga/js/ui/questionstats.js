// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const renderChart = () => {
    const serverData = document.getElementById("question-data")
    const canvas = document.getElementById("question-answers")
    const data = JSON.parse(serverData.dataset.states)
    const url = serverData.dataset.url
    const options = {
      series: data.map(e => e.count),
      labels: data.map(e => e.answer || e.options__answer),
      chart: {
        width: 420,
        type: 'donut',
        events: {
          dataPointSelection: (event, chartContext, config) => {
            const clickedData = data[config.dataPointIndex]
            // The base URL ends in question_<id>=
            window.location.href =
              url + encodeURIComponent(clickedData.answer || clickedData.options)
          },
          dataPointMouseEnter: () => {
            canvas.style.cursor = "pointer"
          },
          dataPointMouseLeave: () => {
            canvas.style.cursor = "inherit"
          },
        },
      },
      dataLabels: {
        enabled: false
      },
      legend: {
        formatter: function(val, opts) {
          if (val.length > 15) val = val.slice(0, 15) + "…"
          return val + " - " + opts.w.globals.series[opts.seriesIndex]
        },
        position: "bottom",
      },
      responsive: [{
        breakpoint: 480,
        options: {
          chart: {
            width: 200
          },
          legend: {
            position: 'bottom'
          }
        }
      }],
      plotOptions: {
        pie: {
          donut: {
            labels: {
              show: true,
              name: {
                formatter: (val) => {
                  if (val.length < 15) return val
                  return val.slice(0, 15) + "…"
                }
              }
            }
          }
        }
      },
      tooltip: {
        enabled: false
      }
    };

    let chart = new ApexCharts(document.querySelector("#question-answers"), options);
    chart.render();
}

onReady(() => renderChart())
