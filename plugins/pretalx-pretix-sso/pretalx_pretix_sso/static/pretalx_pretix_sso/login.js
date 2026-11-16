document.addEventListener("DOMContentLoaded", () => {
  const meta = document.querySelector('meta[name="pretix-sso-login"]')
  const form = document.getElementById("auth-form")
  if (!meta || !form) return
  // "all": pretix replaces password login and registration (wizard)
  // "register": pretix replaces registration only (login page)
  const exclusive = meta.dataset.exclusive

  const block = document.createElement("div")
  block.className = "pretix-sso-login mb-4 text-center"
  const link = document.createElement("a")
  link.className = "btn btn-lg btn-info btn-block"
  link.href = meta.content
  link.textContent = meta.dataset.label
  block.append(link)
  if (exclusive !== "all") {
    const sep = document.createElement("p")
    sep.className = "text-muted mt-3 mb-0"
    sep.textContent = meta.dataset.or
    block.append(sep)
  }
  form.parentNode.insertBefore(block, form)

  // Inline styles, since Bootstrap's display classes override [hidden]
  if (exclusive === "all") {
    form.classList.remove("d-md-flex")
    form.style.display = "none"
    // The wizard's continue/draft buttons would submit the hidden form
    form.closest("form")
      ?.querySelectorAll('button[type="submit"]')
      .forEach((button) => (button.style.display = "none"))
  } else if (exclusive === "register") {
    const register = form.querySelector('[name="register_email"]')?.closest(".auth-form-block")
    if (!register) return
    register.style.display = "none"
    // "I already have an account" makes no sense without the register column
    form.querySelectorAll(".auth-form-block > h4").forEach((h) => (h.style.display = "none"))
    form.classList.remove("d-md-flex")
  }
})
