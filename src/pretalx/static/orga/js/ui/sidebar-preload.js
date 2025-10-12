// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Immediate sidebar state application to prevent layout shift
(function() {
    'use strict';
    
    // Check if sidebar should be expanded based on localStorage
    if (localStorage && localStorage.getItem('sidebarVisible')) {
        // Add a class to document that we can use in CSS
        document.documentElement.classList.add('sidebar-expanded');
    }
})();