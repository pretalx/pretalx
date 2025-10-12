// SPDX-FileCopyrightText: 2023-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Used via the pretalx makemessages command

module.exports = {
  createOldCatalogs: false,
  verbose: true,
  locales: ['en'],
  lexers: {
    vue: [
        {lexer: 'JavascriptLexer', functions: ['$t', 't']},
    ]
  }
}
