# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| pretalx/agenda/apps.py                                                 |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/agenda/context\_processors.py                                  |        2 |        0 |        0 |        0 |    100% |           |
| pretalx/agenda/management/commands/export\_schedule\_html.py           |      167 |        3 |       44 |        3 |     97% |62->61, 70->64, 87->86, 255-257 |
| pretalx/agenda/phrases.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/agenda/recording.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/agenda/rules.py                                                |       31 |        0 |        2 |        0 |    100% |           |
| pretalx/agenda/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| pretalx/agenda/tasks.py                                                |       21 |        0 |        6 |        0 |    100% |           |
| pretalx/agenda/views/featured.py                                       |       25 |        0 |        2 |        0 |    100% |           |
| pretalx/agenda/views/feed.py                                           |       33 |        0 |        2 |        0 |    100% |           |
| pretalx/agenda/views/schedule.py                                       |      136 |        2 |       34 |        1 |     98% |   64, 165 |
| pretalx/agenda/views/speaker.py                                        |       99 |        9 |       18 |        3 |     86% |78, 108-114, 152, 162-163 |
| pretalx/agenda/views/talk.py                                           |      160 |        5 |       24 |        4 |     93% |70->69, 76->69, 155-158, 169-170 |
| pretalx/agenda/views/utils.py                                          |       51 |        6 |       22 |        4 |     86% |21, 59, 61, 65-69, 77->79 |
| pretalx/agenda/views/widget.py                                         |       78 |        7 |       26 |        5 |     88% |39, 84-87, 102, 136->143, 141 |
| pretalx/api/apps.py                                                    |        3 |        0 |        0 |        0 |    100% |           |
| pretalx/api/documentation.py                                           |       28 |        1 |        6 |        2 |     91% |11->26, 27 |
| pretalx/api/exceptions.py                                              |        9 |        0 |        2 |        0 |    100% |           |
| pretalx/api/filters/feedback.py                                        |       16 |        0 |        0 |        0 |    100% |           |
| pretalx/api/filters/review.py                                          |       20 |        0 |        2 |        1 |     95% |  35->exit |
| pretalx/api/filters/schedule.py                                        |       23 |        0 |        4 |        1 |     96% |  41->exit |
| pretalx/api/pagination.py                                              |       23 |        0 |        4 |        0 |    100% |           |
| pretalx/api/permissions.py                                             |       32 |        0 |       14 |        0 |    100% |           |
| pretalx/api/serializers/access\_code.py                                |       19 |        0 |        2 |        0 |    100% |           |
| pretalx/api/serializers/availability.py                                |       20 |        0 |        4 |        0 |    100% |           |
| pretalx/api/serializers/event.py                                       |       21 |        0 |        2 |        0 |    100% |           |
| pretalx/api/serializers/feedback.py                                    |       35 |        1 |        6 |        1 |     95% |        43 |
| pretalx/api/serializers/fields.py                                      |       25 |        0 |        2 |        0 |    100% |           |
| pretalx/api/serializers/log.py                                         |       14 |        0 |        0 |        0 |    100% |           |
| pretalx/api/serializers/mail.py                                        |       29 |        2 |        4 |        0 |     94% |     36-37 |
| pretalx/api/serializers/mixins.py                                      |       38 |        0 |       12 |        0 |    100% |           |
| pretalx/api/serializers/question.py                                    |      122 |        6 |       32 |        1 |     92% |   268-277 |
| pretalx/api/serializers/review.py                                      |       74 |        0 |       12 |        0 |    100% |           |
| pretalx/api/serializers/room.py                                        |       30 |        0 |        4 |        0 |    100% |           |
| pretalx/api/serializers/schedule.py                                    |       71 |        1 |       12 |        1 |     98% |        38 |
| pretalx/api/serializers/speaker.py                                     |       90 |        7 |       26 |        5 |     90% |38, 47, 70, 116, 147-149 |
| pretalx/api/serializers/speaker\_information.py                        |       35 |        1 |        6 |        1 |     95% |        63 |
| pretalx/api/serializers/submission.py                                  |      199 |       22 |       66 |       16 |     85% |81, 93, 119, 162, 176, 307, 313-319, 325->327, 328, 333, 335-337, 346-347, 359, 361-362, 364, 366, 368 |
| pretalx/api/serializers/team.py                                        |       49 |        0 |        8 |        0 |    100% |           |
| pretalx/api/shims.py                                                   |       18 |       18 |        0 |        0 |      0% |     11-35 |
| pretalx/api/versions.py                                                |       30 |        1 |       10 |        1 |     95% |        35 |
| pretalx/api/views/access\_code.py                                      |       27 |        2 |        2 |        0 |     93% |     59-60 |
| pretalx/api/views/event.py                                             |       24 |        0 |        2 |        0 |    100% |           |
| pretalx/api/views/feedback.py                                          |       37 |        1 |       10 |        1 |     96% |        75 |
| pretalx/api/views/mail.py                                              |       15 |        0 |        0 |        0 |    100% |           |
| pretalx/api/views/mixins.py                                            |       77 |        3 |       16 |        6 |     90% |45->47, 62->65, 68->71, 72->76, 106, 116-119 |
| pretalx/api/views/question.py                                          |      115 |        9 |       18 |        3 |     89% |108-112, 159, 172-173, 258-259, 289->301 |
| pretalx/api/views/review.py                                            |       42 |        1 |       10 |        1 |     96% |       112 |
| pretalx/api/views/room.py                                              |       32 |        2 |        2 |        0 |     94% |     65-66 |
| pretalx/api/views/root.py                                              |       19 |        0 |        0 |        0 |    100% |           |
| pretalx/api/views/schedule.py                                          |      129 |        8 |       36 |        8 |     90% |80, 90, 114, 148, 222, 300, 316, 322 |
| pretalx/api/views/speaker.py                                           |       55 |        1 |       12 |        1 |     97% |       157 |
| pretalx/api/views/speaker\_information.py                              |       19 |        0 |        2 |        0 |    100% |           |
| pretalx/api/views/submission.py                                        |      200 |       24 |       20 |        4 |     87% |237, 258, 266, 273, 287-290, 300-303, 313-316, 326-329, 339-342 |
| pretalx/api/views/team.py                                              |       93 |        4 |        8 |        0 |     96% |83-84, 187-188 |
| pretalx/api/views/upload.py                                            |       37 |        5 |        8 |        2 |     84% | 64, 75-78 |
| pretalx/cfp/apps.py                                                    |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/cfp/flow.py                                                    |      478 |        7 |      134 |        4 |     98% |161, 408-410, 646-647, 661, 718->720 |
| pretalx/cfp/forms/auth.py                                              |       26 |        0 |        2 |        0 |    100% |           |
| pretalx/cfp/forms/cfp.py                                               |       20 |        0 |       12 |        2 |     94% |21->20, 38->exit |
| pretalx/cfp/forms/submissions.py                                       |       16 |        0 |        0 |        0 |    100% |           |
| pretalx/cfp/phrases.py                                                 |       21 |        0 |        0 |        0 |    100% |           |
| pretalx/cfp/signals.py                                                 |       11 |        0 |        0 |        0 |    100% |           |
| pretalx/cfp/views/auth.py                                              |       91 |       25 |       10 |        1 |     66% |47, 51, 108, 112-138 |
| pretalx/cfp/views/event.py                                             |       57 |        6 |       10 |        3 |     84% |30, 62, 82, 92-95 |
| pretalx/cfp/views/locale.py                                            |       20 |        1 |        6 |        2 |     88% |21->40, 32 |
| pretalx/cfp/views/robots.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/cfp/views/user.py                                              |      329 |       12 |       64 |       11 |     94% |138, 161, 253, 365, 370, 373->367, 410, 441->445, 449, 461, 463, 482->484, 556-557, 573 |
| pretalx/cfp/views/wizard.py                                            |       82 |        0 |       36 |        0 |    100% |           |
| pretalx/common/apps.py                                                 |       10 |        0 |        0 |        0 |    100% |           |
| pretalx/common/auth.py                                                 |       14 |        3 |        2 |        1 |     75% | 22-23, 26 |
| pretalx/common/cache.py                                                |       48 |        0 |       10 |        0 |    100% |           |
| pretalx/common/checks.py                                               |       63 |       47 |       28 |        0 |     18% |14-52, 57-67, 72-83, 88-112, 117-128, 133-156 |
| pretalx/common/context\_processors.py                                  |       57 |        0 |       14 |        0 |    100% |           |
| pretalx/common/db.py                                                   |       10 |        3 |        0 |        0 |     70% |     19-21 |
| pretalx/common/diff\_utils.py                                          |       49 |        2 |       22 |        3 |     93% |62, 64, 88->81 |
| pretalx/common/exceptions.py                                           |       60 |       38 |       22 |        0 |     27% |56-61, 64-70, 73-81, 86-88, 91, 94-103, 110-113 |
| pretalx/common/exporter.py                                             |       68 |        0 |        0 |        0 |    100% |           |
| pretalx/common/formats/en/formats.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| pretalx/common/forms/fields.py                                         |      172 |        8 |       58 |        9 |     93% |59, 85, 107, 159, 187->exit, 211-212, 273->271, 284, 300 |
| pretalx/common/forms/forms.py                                          |       22 |        0 |        0 |        0 |    100% |           |
| pretalx/common/forms/mixins.py                                         |      294 |       31 |      140 |       29 |     85% |60, 85->79, 171, 222->227, 224, 226, 237-246, 271->276, 368->370, 370->372, 382->384, 384->386, 389->391, 391->393, 407->409, 409->411, 412, 454, 456->475, 462, 467, 486->488, 493-494, 506->508, 534-544, 547, 550-556, 558, 559->529, 563-565 |
| pretalx/common/forms/renderers.py                                      |       18 |        0 |        0 |        0 |    100% |           |
| pretalx/common/forms/tables.py                                         |       23 |        1 |       10 |        1 |     94% |        32 |
| pretalx/common/forms/validators.py                                     |       51 |        0 |        4 |        0 |    100% |           |
| pretalx/common/forms/widgets.py                                        |      172 |        1 |       22 |        1 |     99% |       167 |
| pretalx/common/image.py                                                |      105 |       62 |       40 |        6 |     35% |40-82, 87-90, 101-108, 118-140, 159, 162, 166, 173-180, 186, 191 |
| pretalx/common/language.py                                             |       22 |        0 |        0 |        0 |    100% |           |
| pretalx/common/log\_display.py                                         |       86 |       13 |       38 |        6 |     83% |146-150, 167, 176-181, 183-185, 222, 225 |
| pretalx/common/mail.py                                                 |       54 |        4 |       18 |        2 |     89% |83, 134-136 |
| pretalx/common/management/commands/create\_test\_event.py              |      185 |        5 |       60 |        2 |     96% |150->exit, 155, 163-166 |
| pretalx/common/management/commands/init.py                             |       16 |        0 |        0 |        0 |    100% |           |
| pretalx/common/management/commands/makemessages.py                     |       50 |        6 |       20 |        4 |     83% |45->47, 48-49, 57, 71-73 |
| pretalx/common/management/commands/makemigrations.py                   |       25 |        0 |        4 |        0 |    100% |           |
| pretalx/common/management/commands/migrate.py                          |       13 |        0 |        2 |        0 |    100% |           |
| pretalx/common/management/commands/move\_event.py                      |       29 |        0 |        4 |        1 |     97% |  39->exit |
| pretalx/common/management/commands/rebuild.py                          |       32 |        1 |        2 |        1 |     94% |        56 |
| pretalx/common/management/commands/runperiodic.py                      |        6 |        0 |        0 |        0 |    100% |           |
| pretalx/common/management/commands/shell.py                            |        9 |        0 |        0 |        0 |    100% |           |
| pretalx/common/management/commands/spectacular.py                      |        6 |        0 |        0 |        0 |    100% |           |
| pretalx/common/management/commands/update\_translation\_percentages.py |       39 |       39 |       10 |        0 |      0% |      4-61 |
| pretalx/common/middleware/domains.py                                   |      123 |       14 |       44 |        7 |     84% |45, 79->84, 85, 98-116, 166->172, 172->188, 208-209, 233-238 |
| pretalx/common/middleware/event.py                                     |      112 |       12 |       42 |        4 |     86% |94-96, 118-122, 163-171, 185->exit, 197->exit |
| pretalx/common/models/choices.py                                       |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/common/models/fields.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| pretalx/common/models/file.py                                          |       23 |        2 |        2 |        0 |     84% |     41-43 |
| pretalx/common/models/log.py                                           |       80 |        9 |       32 |        9 |     82% |64-67, 89, 92->96, 101, 104, 109, 113->128, 118->128, 121 |
| pretalx/common/models/mixins.py                                        |      178 |       23 |       72 |        3 |     86% |47, 128, 290->exit, 295-296, 315-318, 321, 324, 327, 330, 334, 337-347 |
| pretalx/common/models/transaction.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| pretalx/common/plugins.py                                              |       27 |        0 |        8 |        1 |     97% |    60->66 |
| pretalx/common/settings/config.py                                      |       23 |        1 |        2 |        1 |     92% |       168 |
| pretalx/common/signals.py                                              |      117 |       14 |       34 |        3 |     89% |37, 79, 174, 180-185, 189-190, 195-197 |
| pretalx/common/tables.py                                               |      314 |       91 |      120 |       15 |     68% |27->exit, 41-52, 61-68, 71, 74-75, 78-105, 143, 175-176, 220->222, 225-226, 229->233, 243-255, 290, 303, 309, 313-316, 383, 394-396, 450, 461->463, 466-467, 481-489, 492-507, 510-517, 525-527, 530-531 |
| pretalx/common/tasks.py                                                |       40 |       14 |       14 |        3 |     57% |27, 38-39, 54-68 |
| pretalx/common/templatetags/copyable.py                                |       11 |        0 |        2 |        0 |    100% |           |
| pretalx/common/templatetags/datetimerange.py                           |       28 |        5 |        6 |        3 |     76% |31, 33, 46-48 |
| pretalx/common/templatetags/event\_tags.py                             |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/common/templatetags/filesize.py                                |       13 |        3 |        4 |        1 |     76% | 13-14, 19 |
| pretalx/common/templatetags/form\_media.py                             |       42 |        6 |       26 |        2 |     79% | 39, 58-67 |
| pretalx/common/templatetags/history\_sidebar.py                        |       77 |       41 |       26 |        8 |     43% |16-24, 32->36, 49-51, 55-60, 72, 74, 84-85, 87-88, 90-91, 93-95, 97-120 |
| pretalx/common/templatetags/html\_signal.py                            |       12 |        0 |        4 |        0 |    100% |           |
| pretalx/common/templatetags/phrases.py                                 |       11 |        1 |        2 |        1 |     85% |        20 |
| pretalx/common/templatetags/rich\_text.py                              |       54 |        1 |        6 |        0 |     98% |       196 |
| pretalx/common/templatetags/safelink.py                                |        6 |        0 |        0 |        0 |    100% |           |
| pretalx/common/templatetags/thumbnail.py                               |        9 |        0 |        0 |        0 |    100% |           |
| pretalx/common/templatetags/times.py                                   |       13 |        0 |        6 |        0 |    100% |           |
| pretalx/common/templatetags/vite.py                                    |       56 |       28 |       24 |        5 |     41% |20-24, 32, 40-58, 69, 74-84, 91 |
| pretalx/common/templatetags/xmlescape.py                               |       14 |        0 |        0 |        0 |    100% |           |
| pretalx/common/text/console.py                                         |       65 |       24 |       18 |        3 |     65% |42-43, 49-50, 64-65, 82, 88-126 |
| pretalx/common/text/css.py                                             |       31 |        0 |       14 |        0 |    100% |           |
| pretalx/common/text/daterange.py                                       |       33 |        0 |       18 |        0 |    100% |           |
| pretalx/common/text/path.py                                            |       19 |        0 |        4 |        0 |    100% |           |
| pretalx/common/text/phrases.py                                         |       60 |        0 |        2 |        0 |    100% |           |
| pretalx/common/text/serialize.py                                       |       23 |        0 |        6 |        0 |    100% |           |
| pretalx/common/ui.py                                                   |       41 |        0 |        0 |        0 |    100% |           |
| pretalx/common/update\_check.py                                        |       67 |        0 |       20 |        0 |    100% |           |
| pretalx/common/views/cache.py                                          |       63 |       11 |       32 |       14 |     74% |20, 26, 53, 76, 78, 80, 86->89, 106->109, 115, 117, 120, 126, 132->138, 139 |
| pretalx/common/views/errors.py                                         |       24 |        0 |        4 |        0 |    100% |           |
| pretalx/common/views/generic.py                                        |      477 |       62 |      136 |       19 |     83% |70-75, 86-96, 137->140, 183-184, 206, 211-212, 293-294, 313, 321-323, 362->exit, 372-374, 411, 414, 417-430, 448->450, 453-455, 459, 498->501, 508->517, 514->517, 589->exit, 615->623, 624-645, 656, 677->679, 685->687, 697 |
| pretalx/common/views/helpers.py                                        |        6 |        0 |        0 |        0 |    100% |           |
| pretalx/common/views/mixins.py                                         |      245 |       73 |       92 |       15 |     65% |35, 39, 41-42, 52-76, 86-87, 103-110, 127, 163-165, 176-180, 185, 195-196, 217, 243, 261-263, 265, 267, 283-293, 301, 335-339, 365-373 |
| pretalx/common/views/redirect.py                                       |       26 |       11 |        6 |        0 |     47% |13-23, 33-43 |
| pretalx/common/views/shortlink.py                                      |       27 |        0 |       16 |        0 |    100% |           |
| pretalx/event/apps.py                                                  |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/event/forms.py                                                 |      146 |        7 |       24 |        3 |     94% |72-75, 128-129, 142, 268-269 |
| pretalx/event/models/event.py                                          |      556 |       31 |      122 |       10 |     93% |84, 463, 468, 514, 517, 655-657, 686->700, 718, 722-733, 755-756, 764, 806-815, 953->956 |
| pretalx/event/models/organiser.py                                      |      119 |        8 |       18 |        6 |     90% |48, 55, 69, 77, 258, 266, 273, 315 |
| pretalx/event/rules.py                                                 |       52 |        0 |       12 |        0 |    100% |           |
| pretalx/event/services.py                                              |       57 |        2 |       20 |        3 |     94% |81, 90->exit, 118 |
| pretalx/event/stages.py                                                |       39 |        0 |       10 |        0 |    100% |           |
| pretalx/event/utils.py                                                 |        7 |        0 |        2 |        0 |    100% |           |
| pretalx/mail/apps.py                                                   |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/mail/context.py                                                |       70 |        4 |       36 |        4 |     92% |31, 42, 61, 74 |
| pretalx/mail/default\_templates.py                                     |       19 |        0 |        0 |        0 |    100% |           |
| pretalx/mail/models.py                                                 |      194 |        8 |       56 |        6 |     94% |34, 242-258, 260, 267, 390, 447 |
| pretalx/mail/placeholders.py                                           |       42 |        4 |        2 |        0 |     91% |16, 28, 50, 65 |
| pretalx/mail/signals.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/apps.py                                                   |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/context\_processors.py                                    |       42 |        0 |       18 |        1 |     98% |    17->14 |
| pretalx/orga/forms/cfp.py                                              |      281 |       51 |       84 |       21 |     76% |88->92, 135->exit, 141, 223, 225, 235-249, 268, 275, 283-316, 382->384, 385, 393, 409->exit, 418->420, 421, 446, 570, 571->exit, 584, 586, 608 |
| pretalx/orga/forms/event.py                                            |      384 |       52 |      114 |       25 |     83% |199, 225-226, 266, 278, 287->295, 297-300, 315, 321->exit, 456, 469-471, 474, 483, 660-668, 700, 718, 741-744, 758-765, 767-770, 800->802, 810-814, 931->exit, 944-946, 968-969, 971, 976-981, 984, 992, 996 |
| pretalx/orga/forms/export.py                                           |       93 |        2 |       34 |        2 |     97% |  125, 145 |
| pretalx/orga/forms/mails.py                                            |      274 |       35 |       90 |       18 |     83% |31->33, 60, 67-68, 76-77, 84-85, 114, 131-132, 135-152, 163, 181->199, 193-194, 219, 254, 316-324, 331, 343-344, 400-401, 432->434, 457->456, 483, 486->489, 500 |
| pretalx/orga/forms/review.py                                           |      277 |       34 |       80 |       17 |     83% |36, 79, 126, 134-135, 148, 156, 163, 165, 221-222, 251, 281-283, 299-305, 365, 395, 412, 434, 491, 496-497, 500->504, 506-507, 513-514, 522 |
| pretalx/orga/forms/schedule.py                                         |      119 |       30 |       14 |        2 |     71% |42->exit, 204, 219, 222-224, 227-229, 232-234, 237-238, 241-242, 245-246, 249-250, 253-254, 257-258, 261, 264, 267, 270, 273, 276, 279 |
| pretalx/orga/forms/speaker.py                                          |       46 |        4 |        2 |        1 |     90% |74, 82, 85, 93 |
| pretalx/orga/forms/submission.py                                       |      165 |       14 |       70 |       12 |     88% |68-70, 111->113, 116, 119->127, 143, 150, 159, 168->170, 177, 201-203, 259, 346-347 |
| pretalx/orga/forms/widgets.py                                          |       35 |        2 |        0 |        0 |     94% |     75-76 |
| pretalx/orga/permissions.py                                            |        3 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/phrases.py                                                |       11 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/receivers.py                                              |       16 |        2 |        4 |        2 |     80% |    17, 29 |
| pretalx/orga/rules.py                                                  |        8 |        0 |        2 |        0 |    100% |           |
| pretalx/orga/signals.py                                                |       28 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/tables/cfp.py                                             |       84 |        4 |        6 |        3 |     92% |70, 92, 258, 260 |
| pretalx/orga/tables/mail.py                                            |       36 |        3 |        2 |        0 |     87% |   110-112 |
| pretalx/orga/tables/organiser.py                                       |       14 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/tables/schedule.py                                        |       17 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/tables/speaker.py                                         |       58 |        4 |        4 |        2 |     90% |42, 45, 51, 150 |
| pretalx/orga/tables/submission.py                                      |      164 |       39 |       58 |        6 |     67% |111->113, 122, 150, 153, 226, 228-229, 235->237, 264-266, 302, 313-317, 320-357 |
| pretalx/orga/templatetags/formsets.py                                  |       16 |        0 |        0 |        0 |    100% |           |
| pretalx/orga/templatetags/orga\_edit\_link.py                          |       10 |        0 |        2 |        0 |    100% |           |
| pretalx/orga/templatetags/platform\_icons.py                           |        9 |        1 |        2 |        1 |     82% |        16 |
| pretalx/orga/templatetags/review\_score.py                             |       17 |        1 |        8 |        1 |     92% |        25 |
| pretalx/orga/utils/i18n.py                                             |       33 |        4 |        8 |        1 |     88% |183-184, 203-204 |
| pretalx/orga/views/auth.py                                             |       59 |        2 |        8 |        2 |     94% |    41, 53 |
| pretalx/orga/views/cards.py                                            |       17 |        0 |        2 |        0 |    100% |           |
| pretalx/orga/views/cfp.py                                              |      390 |       31 |      102 |       24 |     88% |97, 100, 111-112, 116->120, 160, 168, 192, 196, 199->193, 221, 228, 230, 232, 234-236, 266-272, 290, 300->303, 304, 308-319, 375->369, 377->369, 458, 529, 581-582 |
| pretalx/orga/views/dashboard.py                                        |      161 |       28 |       46 |        9 |     78% |31-43, 80, 109-115, 137-138, 157-168, 220, 237-240, 286-287, 296->308, 353-354, 363-370 |
| pretalx/orga/views/event.py                                            |      418 |       28 |      108 |       24 |     89% |153-154, 202, 269, 315, 355, 357->362, 386, 391->389, 406, 414, 418, 424, 454, 458->456, 460, 470-471, 474-478, 481, 581-587, 655, 675, 694-695, 719->718, 722->724, 725 |
| pretalx/orga/views/mails.py                                            |      349 |       54 |       70 |       14 |     80% |52-53, 182-184, 194, 203-205, 255-261, 333-335, 369->377, 373, 399, 404-405, 432, 456, 462-507, 534-536, 551, 557, 570-572, 576, 579, 582-587 |
| pretalx/orga/views/organiser.py                                        |      309 |       40 |       56 |        8 |     81% |118-120, 141-142, 157-158, 166-168, 292-293, 334, 381, 394, 396-412, 426, 429, 434, 439-458, 461, 464-468, 471-473 |
| pretalx/orga/views/person.py                                           |      110 |       19 |       22 |        4 |     80% |77-86, 90-97, 99-107, 152, 160-161 |
| pretalx/orga/views/plugins.py                                          |       36 |        0 |        6 |        0 |    100% |           |
| pretalx/orga/views/review.py                                           |      498 |       70 |      106 |       18 |     83% |85, 88-91, 93-96, 248->250, 250->256, 291->exit, 312-313, 315-321, 354, 363-368, 373, 379-384, 389, 398-412, 434, 448-455, 496-497, 508-509, 520->533, 537, 717-718, 729-732, 734-738, 777, 780, 784, 787-790, 884-885, 888-889, 943, 973-974 |
| pretalx/orga/views/schedule.py                                         |      303 |       27 |       46 |        7 |     88% |51->58, 129-130, 169-176, 348, 349->352, 360, 409, 421, 431, 441-472, 490, 532, 597-604 |
| pretalx/orga/views/speaker.py                                          |      201 |       10 |       22 |        5 |     92% |93-105, 107-110, 234, 308, 371-372 |
| pretalx/orga/views/submission.py                                       |      608 |       31 |      112 |       20 |     92% |193-197, 221, 238-244, 323, 331, 355, 443, 446->440, 483, 506->517, 518, 526->538, 536->538, 596, 624->626, 645->exit, 647, 714-715, 748->758, 800, 854, 881, 1127, 1131, 1135, 1142-1148, 1170-1171 |
| pretalx/orga/views/typeahead.py                                        |       59 |       16 |       16 |        5 |     64% |45, 54, 63, 104-109, 114, 119-131, 154, 193-196 |
| pretalx/person/apps.py                                                 |        5 |        0 |        0 |        0 |    100% |           |
| pretalx/person/exporters.py                                            |       23 |        1 |        4 |        1 |     93% |        33 |
| pretalx/person/forms/auth.py                                           |       42 |        2 |       10 |        2 |     92% |    40, 47 |
| pretalx/person/forms/auth\_token.py                                    |       41 |       17 |       10 |        0 |     51% |55-57, 70-89 |
| pretalx/person/forms/information.py                                    |       21 |        1 |        2 |        1 |     91% |        18 |
| pretalx/person/forms/profile.py                                        |      185 |       31 |       66 |       14 |     78% |67->69, 91-92, 93->96, 100->exit, 121->123, 134, 149, 151, 153, 167, 198->exit, 205, 221-227, 230-231, 283->exit, 301, 327-332, 335-344 |
| pretalx/person/forms/user.py                                           |       57 |        3 |       16 |        3 |     92% |77, 89, 127 |
| pretalx/person/models/auth\_token.py                                   |       73 |       11 |       20 |        0 |     82% |101, 104, 146-155 |
| pretalx/person/models/information.py                                   |       30 |        0 |        0 |        0 |    100% |           |
| pretalx/person/models/preferences.py                                   |       41 |        5 |       18 |        5 |     80% |47-53, 92, 98->exit, 109->112, 112->exit |
| pretalx/person/models/profile.py                                       |       58 |        2 |        6 |        3 |     92% |119, 140, 146->exit, 151->exit, 156->162 |
| pretalx/person/models/user.py                                          |      274 |        6 |       54 |        7 |     96% |88, 246->250, 256->259, 277, 378->380, 383, 451-453, 478->493 |
| pretalx/person/rules.py                                                |       33 |        2 |       10 |        2 |     91% |    44, 46 |
| pretalx/person/services.py                                             |        9 |        0 |        2 |        1 |     91% |    20->22 |
| pretalx/person/signals.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/person/tasks.py                                                |       47 |       17 |       14 |        1 |     57% |     43-65 |
| pretalx/schedule/apps.py                                               |        6 |        0 |        0 |        0 |    100% |           |
| pretalx/schedule/ascii.py                                              |      127 |       30 |       54 |        8 |     71% |66->69, 72->75, 77-81, 92-96, 97->exit, 102-114, 144, 147-168, 182 |
| pretalx/schedule/exporters.py                                          |      119 |        4 |       22 |        0 |     96% |   337-343 |
| pretalx/schedule/forms.py                                              |       54 |        0 |        8 |        1 |     98% |    65->68 |
| pretalx/schedule/ical.py                                               |       37 |        2 |        4 |        0 |     95% |     24-25 |
| pretalx/schedule/models/availability.py                                |       88 |        1 |       34 |        1 |     98% |55, 76->79 |
| pretalx/schedule/models/room.py                                        |       44 |        3 |        4 |        2 |     90% |94, 101, 104 |
| pretalx/schedule/models/schedule.py                                    |      202 |       30 |       68 |        8 |     83% |146-187, 234->236, 278, 282, 352, 364-372, 383-391, 418->420, 510 |
| pretalx/schedule/models/slot.py                                        |      119 |        5 |       22 |        2 |     94% |182-189, 200 |
| pretalx/schedule/notifications.py                                      |       20 |        0 |        4 |        0 |    100% |           |
| pretalx/schedule/phrases.py                                            |       14 |        0 |        0 |        0 |    100% |           |
| pretalx/schedule/services.py                                           |      229 |        5 |       94 |       10 |     95% |72->74, 77->79, 79->81, 81->83, 83->76, 122-124, 128->126, 139->131, 142->144, 144->147, 433-434 |
| pretalx/schedule/signals.py                                            |       24 |        0 |        0 |        0 |    100% |           |
| pretalx/schedule/tasks.py                                              |        9 |        0 |        0 |        0 |    100% |           |
| pretalx/schedule/utils.py                                              |       14 |        0 |        8 |        0 |    100% |           |
| pretalx/submission/apps.py                                             |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/cards.py                                            |       87 |        1 |       10 |        1 |     98% |        34 |
| pretalx/submission/exporters.py                                        |       45 |        0 |        4 |        0 |    100% |           |
| pretalx/submission/forms/comment.py                                    |       18 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/forms/feedback.py                                   |       21 |        0 |        4 |        0 |    100% |           |
| pretalx/submission/forms/question.py                                   |       67 |        0 |       30 |        2 |     98% |87->exit, 109->108 |
| pretalx/submission/forms/resource.py                                   |       25 |        2 |        6 |        2 |     87% |    31, 35 |
| pretalx/submission/forms/submission.py                                 |      204 |       21 |       86 |       14 |     87% |91-92, 99, 142, 156, 161->exit, 166, 187->189, 341, 357-363, 405-418, 420-423, 430, 444-447, 452 |
| pretalx/submission/forms/tag.py                                        |       21 |        0 |        4 |        0 |    100% |           |
| pretalx/submission/icons.py                                            |        1 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/models/access\_code.py                              |       56 |        0 |        4 |        0 |    100% |           |
| pretalx/submission/models/cfp.py                                       |       72 |        0 |        8 |        0 |    100% |           |
| pretalx/submission/models/comment.py                                   |       24 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/models/feedback.py                                  |       20 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/models/question.py                                  |      225 |        8 |       48 |        5 |     94% |371, 375-376, 391, 433->436, 540, 582->589, 584, 587-588 |
| pretalx/submission/models/resource.py                                  |       36 |        0 |        6 |        2 |     95% |59->exit, 66->exit |
| pretalx/submission/models/review.py                                    |      132 |       11 |       26 |        7 |     86% |55-56, 59->exit, 72, 76-78, 95, 98->102, 103, 108, 201, 317 |
| pretalx/submission/models/submission.py                                |      500 |       33 |      122 |       15 |     91% |402-404, 480, 525->545, 531, 533, 537-539, 552-553, 671->677, 693-694, 796->exit, 803, 819-821, 824, 907, 920-935, 984, 1016, 1066-1068, 1079-1084, 1173->exit, 1221->exit |
| pretalx/submission/models/tag.py                                       |       24 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/models/track.py                                     |       34 |        1 |        0 |        0 |     97% |        89 |
| pretalx/submission/models/type.py                                      |       39 |        0 |        4 |        0 |    100% |           |
| pretalx/submission/phrases.py                                          |        8 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/rules.py                                            |      210 |       11 |       56 |        7 |     93% |12-13, 29-30, 217, 224, 255, 267, 296, 373, 388 |
| pretalx/submission/signals.py                                          |        3 |        0 |        0 |        0 |    100% |           |
| pretalx/submission/tasks.py                                            |       15 |        3 |        4 |        2 |     74% | 21-22, 26 |
| tests/agenda/test\_agenda\_permissions.py                              |       22 |        0 |        2 |        0 |    100% |           |
| tests/agenda/test\_agenda\_schedule\_export.py                         |      320 |        2 |       12 |        2 |     99% |    38, 60 |
| tests/agenda/views/test\_agenda\_featured.py                           |       57 |        0 |        4 |        0 |    100% |           |
| tests/agenda/views/test\_agenda\_feedback.py                           |       57 |        0 |        0 |        0 |    100% |           |
| tests/agenda/views/test\_agenda\_schedule.py                           |      240 |        0 |       12 |        0 |    100% |           |
| tests/agenda/views/test\_agenda\_talks.py                              |      197 |        0 |        0 |        0 |    100% |           |
| tests/agenda/views/test\_agenda\_widget.py                             |       42 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_access\_code.py                                   |      116 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_answers.py                                        |      134 |        0 |        2 |        0 |    100% |           |
| tests/api/test\_api\_events.py                                         |       45 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_feedback.py                                       |      167 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_mail.py                                           |      108 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_questions.py                                      |      446 |        0 |        6 |        0 |    100% |           |
| tests/api/test\_api\_reviews.py                                        |      370 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_rooms.py                                          |      205 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_root.py                                           |       13 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_schedule.py                                       |      489 |        0 |        6 |        0 |    100% |           |
| tests/api/test\_api\_speaker\_information.py                           |      141 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_speakers.py                                       |      299 |        0 |        4 |        0 |    100% |           |
| tests/api/test\_api\_submissions.py                                    |      734 |        1 |        2 |        0 |     99% |       112 |
| tests/api/test\_api\_teams.py                                          |      208 |        0 |        0 |        0 |    100% |           |
| tests/api/test\_api\_upload.py                                         |       30 |        0 |        0 |        0 |    100% |           |
| tests/cfp/test\_cfp\_flow.py                                           |       22 |        0 |        0 |        0 |    100% |           |
| tests/cfp/views/test\_cfp\_auth.py                                     |       63 |        0 |        0 |        0 |    100% |           |
| tests/cfp/views/test\_cfp\_base.py                                     |       70 |        0 |        0 |        0 |    100% |           |
| tests/cfp/views/test\_cfp\_user.py                                     |      628 |        0 |       12 |        0 |    100% |           |
| tests/cfp/views/test\_cfp\_view\_flow.py                               |        0 |        0 |        0 |        0 |    100% |           |
| tests/cfp/views/test\_cfp\_wizard.py                                   |      423 |        0 |       18 |        0 |    100% |           |
| tests/common/forms/test\_cfp\_forms\_utils.py                          |        5 |        0 |        0 |        0 |    100% |           |
| tests/common/forms/test\_cfp\_forms\_validators.py                     |       15 |        0 |        4 |        0 |    100% |           |
| tests/common/forms/test\_common\_form\_widgets.py                      |       35 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_cfp\_log.py                                         |       39 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_cfp\_middleware.py                                  |       57 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_cfp\_serialize.py                                   |        5 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_cache.py                                    |       41 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_console.py                                  |       11 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_css.py                                      |       14 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_exporter.py                                 |        6 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_forms\_utils.py                             |        9 |        0 |        2 |        0 |    100% |           |
| tests/common/test\_common\_mail.py                                     |       27 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_management\_commands.py                     |       63 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_middleware\_domains.py                      |       12 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_models\_log.py                              |       76 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_plugins.py                                  |       10 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_signals.py                                  |       34 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_common\_templatetags.py                             |       35 |        0 |        2 |        0 |    100% |           |
| tests/common/test\_common\_utils.py                                    |       25 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_diff\_utils.py                                      |       59 |        0 |        0 |        0 |    100% |           |
| tests/common/test\_update\_check.py                                    |      117 |        0 |        0 |        0 |    100% |           |
| tests/common/views/test\_shortlink.py                                  |       84 |        0 |        0 |        0 |    100% |           |
| tests/conftest.py                                                      |      548 |        0 |       12 |        0 |    100% |           |
| tests/dummy\_app.py                                                    |       14 |        0 |        0 |        0 |    100% |           |
| tests/dummy\_signals.py                                                |       46 |        0 |        6 |        0 |    100% |           |
| tests/event/test\_event\_model.py                                      |      165 |        0 |        0 |        0 |    100% |           |
| tests/event/test\_event\_services.py                                   |      115 |        0 |        0 |        0 |    100% |           |
| tests/event/test\_event\_stages.py                                     |       24 |        0 |        6 |        0 |    100% |           |
| tests/event/test\_event\_utils.py                                      |       11 |        0 |        0 |        0 |    100% |           |
| tests/mail/test\_mail\_models.py                                       |       49 |        0 |        4 |        0 |    100% |           |
| tests/orga/test\_orga\_access.py                                       |       71 |        0 |       12 |        0 |    100% |           |
| tests/orga/test\_orga\_auth.py                                         |      145 |        0 |        0 |        0 |    100% |           |
| tests/orga/test\_orga\_forms.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| tests/orga/test\_orga\_permissions.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| tests/orga/test\_orga\_utils.py                                        |        6 |        0 |        0 |        0 |    100% |           |
| tests/orga/test\_templatetags.py                                       |       18 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_tables.py                                 |      109 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_admin.py                           |       58 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_cfp.py                             |      475 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_dashboard.py                       |      112 |        0 |       40 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_event.py                           |      462 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_mail.py                            |      385 |        0 |       10 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_organiser.py                       |      273 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_person.py                          |       44 |        0 |        2 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_review.py                          |      348 |        0 |        2 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_schedule.py                        |      308 |        0 |        0 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_speaker.py                         |      216 |        0 |        2 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_submission.py                      |      585 |        0 |        6 |        0 |    100% |           |
| tests/orga/views/test\_orga\_views\_submission\_cards.py               |       14 |        0 |        0 |        0 |    100% |           |
| tests/person/test\_auth\_token\_model.py                               |       11 |        0 |        0 |        0 |    100% |           |
| tests/person/test\_information\_model.py                               |        5 |        0 |        0 |        0 |    100% |           |
| tests/person/test\_person\_permissions.py                              |       10 |        0 |        0 |        0 |    100% |           |
| tests/person/test\_person\_tasks.py                                    |       34 |        0 |        0 |        0 |    100% |           |
| tests/person/test\_user\_model.py                                      |       72 |        0 |        0 |        0 |    100% |           |
| tests/schedule/test\_schedule\_availability.py                         |       59 |        0 |        4 |        0 |    100% |           |
| tests/schedule/test\_schedule\_exporters.py                            |       28 |        0 |        0 |        0 |    100% |           |
| tests/schedule/test\_schedule\_forms.py                                |      105 |        0 |       10 |        0 |    100% |           |
| tests/schedule/test\_schedule\_model.py                                |      179 |        0 |        2 |        0 |    100% |           |
| tests/schedule/test\_schedule\_models\_slot.py                         |       75 |        0 |        6 |        0 |    100% |           |
| tests/schedule/test\_schedule\_utils.py                                |       25 |        0 |        2 |        0 |    100% |           |
| tests/services/test\_documentation.py                                  |       37 |        0 |       12 |        0 |    100% |           |
| tests/services/test\_models.py                                         |        8 |        0 |        0 |        0 |    100% |           |
| tests/submission/test\_access\_code\_model.py                          |        7 |        0 |        0 |        0 |    100% |           |
| tests/submission/test\_cfp\_model.py                                   |       15 |        0 |        2 |        0 |    100% |           |
| tests/submission/test\_question\_model.py                              |       59 |        0 |        4 |        0 |    100% |           |
| tests/submission/test\_review\_model.py                                |       19 |        0 |        0 |        0 |    100% |           |
| tests/submission/test\_submission\_model.py                            |      297 |        0 |        6 |        0 |    100% |           |
| tests/submission/test\_submission\_permissions.py                      |       41 |        0 |        0 |        0 |    100% |           |
| tests/submission/test\_submission\_type\_model.py                      |       21 |        0 |        0 |        0 |    100% |           |
|                                                              **TOTAL** | **31619** | **1887** | **5054** |  **700** | **91%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/pretalx/pretalx/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pretalx/pretalx/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fpretalx%2Fpretalx%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.