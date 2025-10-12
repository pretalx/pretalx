// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Heavily inspired by django-formset-js/django-formset-js-improved,
 * with some functionality removed that I did not need, and rewritten
 * as a vanilla JS script to remove my last jQuery dependency. */

(function() {
    "use strict";

    const DEFAULTS = {
        form: '[data-formset-form]',
        emptyForm: 'script[type=form-template][data-formset-empty-form]',
        body: '[data-formset-body]',
        add: '[data-formset-add]',
        deleteButton: '[data-formset-delete-button]',
        hasMaxFormsClass: 'has-max-forms',
        animateForms: false,
        emptyPrefix: '__prefix__'
    };

    class Formset {
        constructor(element, options = {}) {
            this.opts = { ...DEFAULTS, ...options };

            this.formset = element;
            this.emptyForm = this.formset.querySelector(this.opts.emptyForm);
            this.body = this.formset.querySelector(this.opts.body);
            this.addButton = this.formset.querySelector(this.opts.add);

            this.addButton.addEventListener('click', () => this.addForm());
            this.formsetPrefix = element.dataset.formsetPrefix;
            this.formset.addEventListener('formAdded', (e) => {
                if (e.target.matches(this.opts.form)) {
                    this.checkMaxForms();
                }
            });
            this.formset.addEventListener('formDeleted', (e) => {
                if (e.target.matches(this.opts.form)) {
                    this.checkMaxForms();
                }
            });

            this.getForms().forEach((form, index) => {
                this.bindForm(form, index);
            });

            this.checkMaxForms();

            if (this.opts.animateForms) {
                this.setupAnimations();
            }

            element._formset = this;
        }

        addForm() {
            if (this.hasMaxForms()) {
                throw new Error("MAX_NUM_FORMS reached");
            }

            const newIndex = this.totalFormCount();
            this.getManagementForm('TOTAL_FORMS').value = newIndex + 1;

            let newFormHtml = this.emptyForm.innerHTML
                .replace(new RegExp(this.opts.emptyPrefix, 'g'), newIndex)
                .replace(/<\\\/script>/g, '</script>');

            // create temporary container to parse html
            const temp = document.createElement('div');
            temp.innerHTML = newFormHtml;

            // hide before appending to avoid flicker
            if (this.opts.animateForms) {
                Array.from(temp.children).forEach(child => {
                    if (child.matches && child.matches(this.opts.form)) {
                        child.style.display = 'none';
                    }
                });
            }

            while (temp.firstChild) {
                this.body.appendChild(temp.firstChild);
            }

            const forms = this.getForms();
            const newForm = forms[forms.length - 1];
            this.bindForm(newForm, newIndex);
            newForm.dataset.formsetCreatedAtRuntime = 'true';
            return newForm;
        }

        bindForm(form, index) {
            const prefix = `${this.formsetPrefix}-${index}`;
            form.dataset.formsetFormPrefix = prefix;

            const deleteCheckbox = form.querySelector(`[name="${prefix}-DELETE"]`);
            if (!deleteCheckbox) return;

            const onChangeDelete = () => {
                if (deleteCheckbox.checked) {
                    form.dataset.formsetFormDeleted = '';

                    // backup and remove required/pattern attrs
                    form.querySelectorAll('[required]').forEach(field => {
                        field.dataset.formsetRequiredField = 'true';
                        field.required = false;
                    });
                    form.querySelectorAll('input[pattern]').forEach(field => {
                        field.dataset.formsetFieldPattern = field.pattern;
                        field.removeAttribute('pattern');
                    });

                    form.dispatchEvent(new CustomEvent('formDeleted', { bubbles: true }));
                } else {
                    delete form.dataset.formsetFormDeleted;

                    // restore required/pattern attrs
                    form.querySelectorAll('[data-formset-required-field="true"]').forEach(field => {
                        field.required = true;
                    });
                    form.querySelectorAll('[data-formset-field-pattern]').forEach(field => {
                        const pattern = field.dataset.formsetFieldPattern;
                        if (pattern) {
                            field.pattern = pattern;
                        }
                    });

                    form.dispatchEvent(new CustomEvent('formAdded', { bubbles: true }));
                }
            };

            deleteCheckbox.addEventListener('change', onChangeDelete);

            setTimeout(onChangeDelete, 0);

            const deleteButton = form.querySelector(this.opts.deleteButton);
            if (deleteButton) {
                deleteButton.addEventListener('click', () => {
                    deleteCheckbox.checked = true;
                    deleteCheckbox.dispatchEvent(new Event('change'));
                });
            }
        }

        setupAnimations() {
            this.formset.addEventListener('formAdded', (e) => {
                if (!e.target.matches(this.opts.form)) return;

                const form = e.target;
                if (form.dataset.formsetCreatedAtRuntime === 'true') {
                    this.slideDown(form);
                }
            });

            this.formset.addEventListener('formDeleted', (e) => {
                if (!e.target.matches(this.opts.form)) return;
                this.slideUp(e.target);
            });

            this.getForms().forEach(form => {
                if ('formsetFormDeleted' in form.dataset) {
                    form.style.display = 'none';
                }
            });
        }

        slideDown(element) {
            element.style.removeProperty('display');
            let display = window.getComputedStyle(element).display;
            if (display === 'none') display = 'block';
            element.style.display = display;

            const height = element.offsetHeight;
            element.style.overflow = 'hidden';
            element.style.height = 0;
            element.style.paddingTop = 0;
            element.style.paddingBottom = 0;
            element.style.marginTop = 0;
            element.style.marginBottom = 0;
            element.offsetHeight; // force reflow
            element.style.transition = 'height 0.4s ease, padding 0.4s ease, margin 0.4s ease';
            element.style.height = height + 'px';
            element.style.removeProperty('padding-top');
            element.style.removeProperty('padding-bottom');
            element.style.removeProperty('margin-top');
            element.style.removeProperty('margin-bottom');

            setTimeout(() => {
                element.style.removeProperty('height');
                element.style.removeProperty('overflow');
                element.style.removeProperty('transition');
            }, 400);
        }

        slideUp(element) {
            element.style.overflow = 'hidden';
            element.style.height = element.offsetHeight + 'px';
            element.offsetHeight; // force reflow
            element.style.transition = 'height 0.4s ease, padding 0.4s ease, margin 0.4s ease';
            element.style.height = 0;
            element.style.paddingTop = 0;
            element.style.paddingBottom = 0;
            element.style.marginTop = 0;
            element.style.marginBottom = 0;

            setTimeout(() => {
                element.style.display = 'none';
                element.style.removeProperty('height');
                element.style.removeProperty('overflow');
                element.style.removeProperty('transition');
                element.style.removeProperty('padding-top');
                element.style.removeProperty('padding-bottom');
                element.style.removeProperty('margin-top');
                element.style.removeProperty('margin-bottom');
            }, 400);
        }

        getForms() {
            return Array.from(this.body.querySelectorAll(this.opts.form));
        }

        getActiveForms() {
            return this.getForms().filter(form => !('formsetFormDeleted' in form.dataset));
        }

        getManagementForm(name) {
            return this.formset.querySelector(`[name="${this.formsetPrefix}-${name}"]`);
        }

        totalFormCount() {
            return this.getForms().length;
        }

        deletedFormCount() {
            return this.getForms().filter(form => 'formsetFormDeleted' in form.dataset).length;
        }

        activeFormCount() {
            return this.totalFormCount() - this.deletedFormCount();
        }

        hasMaxForms() {
            const maxFormsField = this.getManagementForm('MAX_NUM_FORMS');
            const maxForms = maxFormsField ? parseInt(maxFormsField.value, 10) : 1000;
            return this.activeFormCount() >= maxForms;
        }

        checkMaxForms() {
            if (this.hasMaxForms()) {
                this.formset.classList.add(this.opts.hasMaxFormsClass);
                this.addButton.disabled = true;
            } else {
                this.formset.classList.remove(this.opts.hasMaxFormsClass);
                this.addButton.disabled = false;
            }
        }

        static getOrCreate(element, options) {
            return element._formset || new Formset(element, options);
        }
    }

    // auto-initialize
    onReady(() => {
        document.querySelectorAll('[data-formset]').forEach(element => {
            Formset.getOrCreate(element, { animateForms: true });
        });
    });

    // expose globally
    window.Formset = Formset;
})();
