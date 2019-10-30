document.addEventListener("DOMContentLoaded", function() {
  function updateNowlines() {
    const now = moment()
    document.querySelectorAll(".pretalx-schedule-nowline").forEach(element => {
      const start = moment(element.parentElement.parentElement.dataset.start)
      const diff_seconds = now.diff(start, "seconds")
      const diff_px = (diff_seconds / 60 / 60) * 120
      element.style.top = diff_px + "px"
    })
  }

  function updateCurrentTalk() {
    const now = moment()
    document.querySelectorAll(".pretalx-schedule-talk").forEach(element => {
      const start = moment(element.dataset.start)
      const end = moment(element.dataset.end)
      if (start < now && end > now) {
        element.classList.add("active")
      } else {
        element.classList.remove("active")
      }
    })
  }

  updateNowlines()
  document.querySelectorAll(".pretalx-schedule-nowline").forEach(element => {
    element.style.visibility = "visible"
  })

  updateCurrentTalk()

  setInterval(updateNowlines, 60 * 60)
  setInterval(updateCurrentTalk, 60 * 60)
})
