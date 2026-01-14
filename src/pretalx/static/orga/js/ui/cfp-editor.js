// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

const CfpEditorNav = {
    getSteps() {
        return Array.from(document.querySelectorAll('#submission-steps .step[data-step]'));
    },
    getCurrentStepIndex() {
        return this.getSteps().findIndex(step => step.classList.contains('step-current'));
    },

    updateStagesIndicator(newStepId) {
        const steps = this.getSteps();
        let found = false;
        steps.forEach(step => {
            const stepId = step.dataset.step;
            step.classList.remove('step-current', 'step-done', 'step-tbd');
            if (stepId === newStepId) {
                step.classList.add('step-current');
                found = true;
            } else if (!found) {
                step.classList.add('step-done');
            } else {
                step.classList.add('step-tbd');
            }
        });
        this.updateNavButtons();
    },

    updateNavButtons() {
        const steps = this.getSteps();
        const currentIndex = this.getCurrentStepIndex();
        const prevBtn = document.getElementById('cfp-nav-prev');
        const nextBtn = document.getElementById('cfp-nav-next');

        if (prevBtn) {
            prevBtn.disabled = currentIndex <= 0;
        }
        if (nextBtn) {
            nextBtn.disabled = currentIndex >= steps.length - 1;
        }
    },

    navigateToPrev() {
        const steps = this.getSteps();
        const currentIndex = this.getCurrentStepIndex();
        if (currentIndex > 0) {
            steps[currentIndex - 1].click();
            steps[currentIndex - 1].focus();
        }
    },

    navigateToNext() {
        const steps = this.getSteps();
        const currentIndex = this.getCurrentStepIndex();
        if (currentIndex < steps.length - 1) {
            steps[currentIndex + 1].click();
            steps[currentIndex + 1].focus();
        }
    },

    handleKeyboardNav(e) {
        const steps = this.getSteps();
        const currentIndex = steps.indexOf(e.target);
        if (currentIndex === -1) return;

        let targetIndex = -1;
        switch (e.key) {
            case 'ArrowLeft':
            case 'ArrowUp':
                targetIndex = currentIndex > 0 ? currentIndex - 1 : steps.length - 1;
                break;
            case 'ArrowRight':
            case 'ArrowDown':
                targetIndex = currentIndex < steps.length - 1 ? currentIndex + 1 : 0;
                break;
            case 'Home':
                targetIndex = 0;
                break;
            case 'End':
                targetIndex = steps.length - 1;
                break;
            case 'Enter':
            case ' ':
                e.preventDefault();
                steps[currentIndex].click();
                return;
            default:
                return;
        }

        if (targetIndex !== -1) {
            e.preventDefault();
            steps[targetIndex].focus();
        }
    }
};

document.body.addEventListener('htmx:configRequest', (e) => {
    const csrfToken = getCookie('pretalx_csrftoken')
    e.detail.headers['X-CSRFToken'] = csrfToken
})

const showErrorInTarget = (target, message) => {
    if (target && target.id === 'field-modal-content') {
        const errorDiv = document.createElement('div')
        errorDiv.className = 'alert alert-danger'
        errorDiv.textContent = message
        target.replaceChildren(errorDiv)
    } else {
        alert(message)
    }
}

document.body.addEventListener('htmx:responseError', (e) => {
    const status = e.detail.xhr.status
    let message = 'An error occurred while saving. Please try again.'

    if (status === 403) {
        message = 'Permission denied. Please check that you are still logged in.'
    } else if (status === 404) {
        message = 'The requested resource was not found.'
    } else if (status >= 500) {
        message = 'A server error occurred. Please try again later.'
    }

    showErrorInTarget(e.detail.target, message)
})
document.body.addEventListener('htmx:sendError', (e) => {
    showErrorInTarget(e.detail.target, 'Network error. Please check your connection and try again.')
})
document.body.addEventListener('htmx:timeout', (e) => {
    showErrorInTarget(e.detail.target, 'The request timed out. Please try again.')
})

document.body.addEventListener('htmx:afterSwap', (e) => {
    initDragsort(e.detail.target)
    if (e.detail.target.id === 'step-content-inner') {
        const stepContentInner = e.detail.target.querySelector('.step-content-inner')
        if (stepContentInner) {
            const stepId = stepContentInner.id.replace('step-', '')
            CfpEditorNav.updateStagesIndicator(stepId)
        }
        const modal = document.getElementById('field-modal')
        if (modal && modal.open) {
            modal.close()
        }
    }
})

document.body.addEventListener('click', (e) => {
    if (e.target.closest('#cfp-nav-prev')) {
        e.preventDefault()
        CfpEditorNav.navigateToPrev()
        return
    }
    if (e.target.closest('#cfp-nav-next')) {
        e.preventDefault()
        CfpEditorNav.navigateToNext()
        return
    }

    if (e.target.closest('.dialog-close')) {
        const dialog = e.target.closest('dialog')
        if (dialog) dialog.close()
        return
    }
    if (e.target.closest('.dialog-cancel')) {
        const dialog = e.target.closest('dialog')
        if (dialog) dialog.close()
        return
    }
    const dialogTrigger = e.target.closest('[data-dialog-target]')
    if (dialogTrigger) {
        const dialog = document.querySelector(dialogTrigger.dataset.dialogTarget)
        if (dialog) {
            e.preventDefault()
            const content = dialog.querySelector('#field-modal-content')
            if (content) {
                const loadingTemplate = content.querySelector('.dialog-loading')
                if (loadingTemplate) {
                    const loading = loadingTemplate.cloneNode(true)
                    loading.querySelector(".loading-spinner")?.classList.add("loading-spinner-md")
                    content.replaceChildren(loading)
                }
            }
            dialog.showModal()
        }
    }
})

onReady(() => {
    CfpEditorNav.updateNavButtons()
    const stepsContainer = document.getElementById('submission-steps')
    if (stepsContainer) {
        stepsContainer.addEventListener('keydown', (e) => CfpEditorNav.handleKeyboardNav(e))
    }
})
