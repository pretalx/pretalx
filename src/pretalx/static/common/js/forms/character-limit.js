// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const normalizeLineBreaks = (text) => text.replace(/\r\n/g, '\n');

    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const createWrapper = (element, wrapperClass, elementClass) => {
        const parentEl = element.closest('.form-group') || element.parentElement;
        let wrapper = parentEl.querySelector(`.${wrapperClass}`);

        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = wrapperClass;
            element.parentElement.insertBefore(wrapper, element);
            wrapper.appendChild(element);
            if (elementClass) {
                element.classList.add(elementClass);
            }
        }
        return wrapper;
    };

    const updateCounter = (element, current, max) => {
        const isTextarea = element.tagName === 'TEXTAREA';
        const wrapperClass = isTextarea ? 'character-limit-highlight-wrapper' : 'character-limit-input-wrapper';
        const counterParent = element.closest(`.${wrapperClass}`);
        let counter = counterParent?.querySelector('.character-counter');

        if (!counter) {
            counter = document.createElement('div');
            const counterType = isTextarea ? 'textarea' : 'input';
            counter.className = `character-counter character-counter-${counterType} text-small text-danger`;
            counterParent?.appendChild(counter);
        }

        const isOverLimit = current > max;
        const showCounter = current >= (max * 0.8);

        counter.style.display = showCounter ? 'block' : 'none';
        if (showCounter) {
            counter.textContent = `${current}/${max}`;
        }

        return isOverLimit;
    };

    const updateValidationState = (element, isInvalid) => {
        if (isInvalid) {
            element.setAttribute('aria-invalid', 'true');
            element.classList.add('is-invalid');
        } else {
            element.removeAttribute('aria-invalid');
            element.classList.remove('is-invalid');
        }
    };

    const updateTextareaHighlight = (textarea, maxLength) => {
        if (textarea.tagName !== 'TEXTAREA') return;

        const highlightWrapper = createWrapper(textarea, 'character-limit-highlight-wrapper', 'character-limit-textarea');
        let highlightDiv = highlightWrapper.querySelector('.character-limit-highlight');

        if (!highlightDiv) {
            highlightDiv = document.createElement('div');
            highlightDiv.className = 'character-limit-highlight';
            highlightWrapper.insertBefore(highlightDiv, textarea);

            // Copy computed styles for reliable alignment
            const computedStyle = window.getComputedStyle(textarea);
            ['padding-top', 'padding-right', 'padding-bottom', 'padding-left',
             'font-family', 'font-size', 'font-weight', 'font-style',
             'line-height', 'letter-spacing', 'word-spacing',
             'border-width', 'box-sizing'].forEach(style => {
                highlightDiv.style[style] = computedStyle[style];
            });

            // Sync scrolling
            textarea.addEventListener('scroll', () => {
                highlightDiv.scrollTop = textarea.scrollTop;
                highlightDiv.scrollLeft = textarea.scrollLeft;
            });
        }

        const normalizedValue = normalizeLineBreaks(textarea.value);
        const currentLength = normalizedValue.length;

        if (currentLength > maxLength) {
            const validText = normalizedValue.substring(0, maxLength);
            const excessText = normalizedValue.substring(maxLength);
            highlightDiv.innerHTML =
                escapeHtml(validText) +
                '<mark class="character-limit-excess">' + escapeHtml(excessText) + '</mark>';
            highlightDiv.style.display = 'block';
        } else {
            highlightDiv.style.display = 'none';
        }
    };

    const updateInputHighlight = (input, maxLength) => {
        if (input.tagName !== 'INPUT') return;

        const highlightWrapper = createWrapper(input, 'character-limit-input-wrapper', 'character-limit-input');
        let highlightDiv = highlightWrapper.querySelector('.character-limit-highlight-input');

        if (!highlightDiv) {
            highlightDiv = document.createElement('div');
            highlightDiv.className = 'character-limit-highlight-input';
            highlightWrapper.insertBefore(highlightDiv, input);

            // Copy computed styles for reliable alignment
            const computedStyle = window.getComputedStyle(input);
            ['padding-top', 'padding-right', 'padding-bottom', 'padding-left',
             'font-family', 'font-size', 'font-weight', 'font-style',
             'line-height', 'letter-spacing', 'word-spacing',
             'border-width', 'box-sizing'].forEach(style => {
                highlightDiv.style[style] = computedStyle[style];
            });

            // Sync horizontal scrolling for inputs
            input.addEventListener('scroll', () => {
                highlightDiv.scrollLeft = input.scrollLeft;
            });
        }

        const normalizedValue = normalizeLineBreaks(input.value);
        const currentLength = normalizedValue.length;

        if (currentLength > maxLength) {
            const validText = normalizedValue.substring(0, maxLength);
            const excessText = normalizedValue.substring(maxLength);
            highlightDiv.innerHTML =
                escapeHtml(validText) +
                '<mark class="character-limit-excess">' + escapeHtml(excessText) + '</mark>';
            highlightDiv.style.display = 'block';
            // Sync scroll position
            highlightDiv.scrollLeft = input.scrollLeft;
        } else {
            highlightDiv.style.display = 'none';
        }
    };

    const validateField = (element) => {
        const maxLength = parseInt(element.dataset.maxlength, 10);
        if (!maxLength) return true;

        const currentLength = normalizeLineBreaks(element.value).length;
        if (element.tagName === 'TEXTAREA') {
            updateTextareaHighlight(element, maxLength);
        } else if (element.tagName === 'INPUT') {
            updateInputHighlight(element, maxLength);
        }

        const isOverLimit = updateCounter(element, currentLength, maxLength);
        updateValidationState(element, isOverLimit);

        return !isOverLimit;
    };

    const initializeField = (element) => {
        if (element.hasAttribute('maxlength')) {
            element.removeAttribute('maxlength');
        }
        validateField(element);
        ['input', 'change', 'paste'].forEach(eventType => {
            element.addEventListener(eventType, () => {
                // Small delay for paste events to allow content to be inserted
                setTimeout(() => validateField(element), 0);
            });
        });
    };

    document.querySelectorAll('[data-maxlength]').forEach(initializeField);
})
