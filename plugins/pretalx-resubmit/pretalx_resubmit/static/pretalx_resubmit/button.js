document.addEventListener("DOMContentLoaded", () => {
  const meta = document.querySelector('meta[name="pretalx-resubmit"]')
  const links = document.querySelector(".url-links")
  if (!meta || !links) return
  const link = document.createElement("a")
  link.className = "btn btn-info btn-lg btn-block"
  link.href = meta.content
  link.textContent = meta.dataset.label
  // Next to "Submit a proposal", which is the last button
  const submit = links.querySelector("a.btn-success:last-child")
  links.insertBefore(link, submit)
})
