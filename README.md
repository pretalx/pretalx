# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/pretalx/agenda/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/context\_processors.py                                  |        2 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/management/commands/export\_schedule\_html.py           |      167 |        3 |       44 |        3 |     97% |64->63, 72->66, 89->88, 255-257 |
| src/pretalx/agenda/phrases.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/recording.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/rules.py                                                |       31 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/tasks.py                                                |       33 |        0 |        8 |        2 |     95% |42->exit, 44->exit |
| src/pretalx/agenda/views/featured.py                                       |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/feed.py                                           |       34 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/schedule.py                                       |      136 |        2 |       34 |        1 |     98% |   64, 144 |
| src/pretalx/agenda/views/speaker.py                                        |       90 |        8 |       18 |        3 |     86% |84-90, 126, 131-132, 144->exit |
| src/pretalx/agenda/views/talk.py                                           |      154 |        3 |       18 |        3 |     95% |70->69, 76->69, 148-151 |
| src/pretalx/agenda/views/utils.py                                          |       50 |        6 |       22 |        4 |     86% |21, 59, 61, 65-69, 77->79 |
| src/pretalx/agenda/views/widget.py                                         |       83 |        6 |       28 |        3 |     92% |48, 92-95, 110 |
| src/pretalx/api/apps.py                                                    |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/documentation.py                                           |       26 |        0 |        4 |        1 |     97% |    11->26 |
| src/pretalx/api/exceptions.py                                              |        9 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/filters/answer.py                                          |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/feedback.py                                        |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/review.py                                          |       27 |        0 |        2 |        1 |     97% |  65->exit |
| src/pretalx/api/filters/schedule.py                                        |       23 |        0 |        4 |        1 |     96% |  39->exit |
| src/pretalx/api/filters/submission.py                                      |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/pagination.py                                              |       23 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/permissions.py                                             |       33 |        0 |       16 |        1 |     98% |    50->57 |
| src/pretalx/api/serializers/access\_code.py                                |       72 |        2 |       20 |        0 |     98% |     51-52 |
| src/pretalx/api/serializers/availability.py                                |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/event.py                                       |       23 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/feedback.py                                    |       36 |        1 |        6 |        1 |     95% |        44 |
| src/pretalx/api/serializers/fields.py                                      |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/log.py                                         |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/serializers/mail.py                                        |       29 |        2 |        4 |        0 |     94% |     29-30 |
| src/pretalx/api/serializers/mixins.py                                      |       38 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/question.py                                    |      126 |        7 |       32 |        2 |     91% |264-273, 306 |
| src/pretalx/api/serializers/review.py                                      |       74 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/room.py                                        |       30 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/schedule.py                                    |       71 |        1 |       12 |        1 |     98% |        39 |
| src/pretalx/api/serializers/speaker.py                                     |       91 |        4 |       28 |        4 |     93% |36, 76, 110, 136 |
| src/pretalx/api/serializers/speaker\_information.py                        |       35 |        1 |        6 |        1 |     95% |        63 |
| src/pretalx/api/serializers/submission.py                                  |      235 |       21 |       74 |       15 |     88% |115, 127, 153, 203, 217, 361-367, 373->375, 376, 381, 383-385, 394-395, 407, 409-410, 412, 414, 416 |
| src/pretalx/api/serializers/team.py                                        |       49 |        0 |        8 |        0 |    100% |           |
| src/pretalx/api/shims.py                                                   |       18 |       18 |        0 |        0 |      0% |     11-35 |
| src/pretalx/api/versions.py                                                |       30 |        1 |       10 |        1 |     95% |        32 |
| src/pretalx/api/views/access\_code.py                                      |       24 |        2 |        0 |        0 |     92% |     59-60 |
| src/pretalx/api/views/event.py                                             |       24 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/feedback.py                                          |       37 |        1 |       10 |        1 |     96% |        74 |
| src/pretalx/api/views/mail.py                                              |       15 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/mixins.py                                            |       77 |        3 |       16 |        6 |     90% |45->47, 62->65, 68->71, 72->76, 104, 114-117 |
| src/pretalx/api/views/question.py                                          |      103 |        9 |       16 |        3 |     88% |102-106, 153, 166-167, 234-235, 265->277 |
| src/pretalx/api/views/review.py                                            |       45 |        1 |       12 |        1 |     96% |       113 |
| src/pretalx/api/views/room.py                                              |       35 |        2 |        4 |        0 |     95% |     68-69 |
| src/pretalx/api/views/root.py                                              |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/schedule.py                                          |      129 |        8 |       36 |        8 |     90% |80, 90, 114, 148, 219, 297, 313, 319 |
| src/pretalx/api/views/speaker.py                                           |       57 |        1 |       12 |        1 |     97% |       148 |
| src/pretalx/api/views/speaker\_information.py                              |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/submission.py                                        |      243 |       18 |       30 |        5 |     91% |245, 266, 270, 292, 305-306, 314-315, 323-324, 332-333, 341-342, 396-399 |
| src/pretalx/api/views/team.py                                              |       91 |        4 |        6 |        0 |     96% |82-83, 188-189 |
| src/pretalx/api/views/upload.py                                            |       37 |        5 |        8 |        2 |     84% | 58, 69-72 |
| src/pretalx/cfp/apps.py                                                    |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/flow.py                                                    |      649 |       14 |      208 |       16 |     96% |177, 256, 432->426, 478, 532, 534, 569->582, 571->570, 573-574, 616-618, 781->exit, 866, 880, 886->889, 947, 951, 967->969, 969->979 |
| src/pretalx/cfp/forms/auth.py                                              |       26 |        0 |        2 |        0 |    100% |           |
| src/pretalx/cfp/forms/cfp.py                                               |       30 |        2 |       18 |        1 |     94% |    47, 53 |
| src/pretalx/cfp/forms/submissions.py                                       |       43 |        4 |       10 |        1 |     87% |     53-56 |
| src/pretalx/cfp/phrases.py                                                 |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/signals.py                                                 |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/auth.py                                              |       91 |       25 |       10 |        1 |     66% |47, 51, 108, 112-138 |
| src/pretalx/cfp/views/event.py                                             |       57 |        6 |       10 |        3 |     84% |30, 62, 82, 92-95 |
| src/pretalx/cfp/views/locale.py                                            |       19 |        0 |        4 |        1 |     96% |    21->38 |
| src/pretalx/cfp/views/robots.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/user.py                                              |      364 |       18 |       64 |       11 |     93% |140, 162, 234-236, 260, 303-305, 378, 383, 386->380, 426-427, 468->472, 476, 488, 490, 507->509, 617-618 |
| src/pretalx/cfp/views/wizard.py                                            |       75 |        0 |       34 |        0 |    100% |           |
| src/pretalx/common/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/auth.py                                                 |       20 |        3 |        4 |        1 |     83% | 31-32, 35 |
| src/pretalx/common/cache.py                                                |       58 |        4 |       10 |        0 |     94% |56, 59, 62, 65 |
| src/pretalx/common/checks.py                                               |       66 |       40 |       30 |        3 |     32% |16-54, 59-69, 74-85, 91, 96-97, 106, 128-139, 144-167 |
| src/pretalx/common/context\_processors.py                                  |       57 |        0 |       14 |        0 |    100% |           |
| src/pretalx/common/db.py                                                   |       10 |        3 |        0 |        0 |     70% |     19-21 |
| src/pretalx/common/diff\_utils.py                                          |       42 |        0 |       12 |        1 |     98% |    84->77 |
| src/pretalx/common/exceptions.py                                           |       57 |       35 |       20 |        0 |     29% |55-60, 63-69, 72-80, 85-87, 90, 93-102, 109 |
| src/pretalx/common/exporter.py                                             |       63 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/formats/en/formats.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/fields.py                                         |      279 |       17 |      102 |       16 |     91% |70, 96, 118, 189-190, 204->exit, 206, 213, 224, 241->244, 244->exit, 288, 341->exit, 346, 359-360, 386-387, 389-390, 444->442, 470 |
| src/pretalx/common/forms/forms.py                                          |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/mixins.py                                         |      307 |       30 |      150 |       30 |     86% |67->61, 114, 160, 250->255, 252, 254, 265-274, 299->304, 395->397, 397->399, 409->411, 411->413, 416->418, 418->420, 434->436, 436->438, 439, 482, 484->503, 490, 495, 514->516, 521-522, 534->536, 563-573, 576, 579-585, 587, 588->558, 592-594, 608->600 |
| src/pretalx/common/forms/renderers.py                                      |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/tables.py                                         |       40 |        1 |       16 |        2 |     95% |51, 90->95 |
| src/pretalx/common/forms/validators.py                                     |       50 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/forms/widgets.py                                        |      295 |        5 |       42 |        5 |     97% |252, 285, 406, 556, 567 |
| src/pretalx/common/image.py                                                |       97 |       28 |       34 |        7 |     64% |24-66, 89, 91, 104, 118->122, 122->exit, 143, 146, 170 |
| src/pretalx/common/language.py                                             |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/log\_display.py                                         |       86 |       10 |       38 |        6 |     87% |171, 185, 194-199, 201-203, 240, 243 |
| src/pretalx/common/mail.py                                                 |       94 |       18 |       26 |        4 |     78% |64-66, 75-77, 108, 161-163, 175-181, 186 |
| src/pretalx/common/management/commands/create\_test\_event.py              |      173 |        5 |       48 |        2 |     96% |148->exit, 153, 159-162 |
| src/pretalx/common/management/commands/devserver.py                        |       15 |       15 |        4 |        0 |      0% |     10-39 |
| src/pretalx/common/management/commands/init.py                             |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/makemessages.py                     |       45 |        6 |       16 |        3 |     82% |47-48, 56, 70-72 |
| src/pretalx/common/management/commands/makemigrations.py                   |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/management/commands/migrate.py                          |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/management/commands/move\_event.py                      |       27 |        0 |        2 |        1 |     97% |  36->exit |
| src/pretalx/common/management/commands/rebuild.py                          |       33 |        2 |        0 |        0 |     94% |     49-50 |
| src/pretalx/common/management/commands/runperiodic.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/sendtestemail.py                    |       14 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/management/commands/shell.py                            |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/spectacular.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/update\_translation\_percentages.py |       31 |       31 |        6 |        0 |      0% |      4-41 |
| src/pretalx/common/middleware/domains.py                                   |      121 |       14 |       42 |        7 |     83% |45, 79->84, 85, 98-116, 166->172, 172->188, 208-209, 233-238 |
| src/pretalx/common/middleware/event.py                                     |      123 |       12 |       48 |        4 |     87% |103-105, 140-144, 185-193, 207->exit, 219->exit |
| src/pretalx/common/models/fields.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/models/file.py                                          |       23 |        1 |        2 |        1 |     92% |        46 |
| src/pretalx/common/models/log.py                                           |       71 |        7 |       28 |        8 |     85% |83, 89->93, 98, 101, 106, 110->125, 115->125, 118, 123-124 |
| src/pretalx/common/models/mixins.py                                        |      207 |       27 |       84 |        6 |     85% |48, 129, 308, 325->323, 349, 352->exit, 357-360, 379-382, 385, 388, 391, 394, 398, 401-411 |
| src/pretalx/common/models/transaction.py                                   |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/plugins.py                                              |       30 |        0 |        8 |        1 |     97% |    63->69 |
| src/pretalx/common/settings/config.py                                      |       23 |        1 |        2 |        1 |     92% |        85 |
| src/pretalx/common/signals.py                                              |      116 |       14 |       34 |        3 |     89% |38, 80, 175, 181-186, 190-191, 196-198 |
| src/pretalx/common/tables.py                                               |      402 |       50 |      168 |       26 |     85% |61, 63->65, 76-77, 80-81, 135->133, 140->142, 164, 208-209, 253, 260, 286, 289-291, 294->297, 301-308, 322, 396->400, 438-440, 473, 478, 491, 497, 501-504, 571, 582-584, 635, 646->648, 651-652, 670->672, 700-702, 708, 713, 723-725, 728-729 |
| src/pretalx/common/tasks.py                                                |       40 |        4 |       14 |        5 |     83% |28, 57, 62, 68, 71->exit |
| src/pretalx/common/templatetags/copyable.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/templatetags/datetimerange.py                           |       28 |        5 |        6 |        3 |     76% |31, 33, 46-48 |
| src/pretalx/common/templatetags/event\_tags.py                             |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/filesize.py                                |       13 |        3 |        4 |        1 |     76% | 13-14, 19 |
| src/pretalx/common/templatetags/form\_media.py                             |       42 |        6 |       24 |        2 |     79% | 39, 58-67 |
| src/pretalx/common/templatetags/history\_sidebar.py                        |       77 |       41 |       26 |        8 |     43% |16-24, 32->36, 49-51, 55-60, 72, 74, 84-85, 87-88, 90-91, 93-95, 97-120 |
| src/pretalx/common/templatetags/html\_signal.py                            |       11 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/templatetags/phrases.py                                 |       10 |        1 |        0 |        0 |     90% |        20 |
| src/pretalx/common/templatetags/rich\_text.py                              |       58 |        1 |        8 |        0 |     98% |       201 |
| src/pretalx/common/templatetags/safelink.py                                |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/thumbnail.py                               |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/times.py                                   |       13 |        0 |        6 |        0 |    100% |           |
| src/pretalx/common/templatetags/vite.py                                    |       37 |       20 |       16 |        2 |     36% |20-24, 32, 40-58 |
| src/pretalx/common/templatetags/xmlescape.py                               |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/text/console.py                                         |       66 |       24 |       18 |        3 |     65% |45-46, 52-53, 67-68, 85, 91-127 |
| src/pretalx/common/text/css.py                                             |       28 |        0 |       12 |        0 |    100% |           |
| src/pretalx/common/text/daterange.py                                       |       33 |        0 |       18 |        0 |    100% |           |
| src/pretalx/common/text/path.py                                            |       21 |        4 |        6 |        2 |     70% |32->40, 35-38 |
| src/pretalx/common/text/phrases.py                                         |       58 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/text/serialize.py                                       |       27 |        1 |        8 |        1 |     94% |        40 |
| src/pretalx/common/text/xml.py                                             |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/ui.py                                                   |       52 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/update\_check.py                                        |       66 |        0 |       20 |        0 |    100% |           |
| src/pretalx/common/views/cache.py                                          |       60 |       10 |       28 |       12 |     75% |20, 26, 53, 76, 78, 84->87, 104->107, 113, 115, 118, 124, 130->136, 137 |
| src/pretalx/common/views/errors.py                                         |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/views/generic.py                                        |      474 |       56 |      130 |       22 |     85% |73, 75, 76->69, 89-90, 94-98, 141->144, 180, 193-194, 222-223, 304-305, 325, 328, 335-337, 370->exit, 380-382, 419, 422, 425-438, 456->458, 461-463, 506->509, 516->525, 522->525, 631->639, 640-662, 676->684, 688, 710, 721, 746->748, 758 |
| src/pretalx/common/views/helpers.py                                        |        8 |        1 |        0 |        0 |     88% |        31 |
| src/pretalx/common/views/mixins.py                                         |      319 |       81 |      114 |       14 |     71% |41, 45, 58-82, 92-93, 109-116, 133, 169-170, 184-188, 193, 203-204, 225, 251, 269, 283-302, 309, 343-347, 374, 387-390, 426, 431-438, 469-470, 494, 507-509 |
| src/pretalx/common/views/redirect.py                                       |       26 |       11 |        6 |        0 |     47% |13-23, 33-38 |
| src/pretalx/common/views/shortlink.py                                      |       30 |        0 |       18 |        0 |    100% |           |
| src/pretalx/event/apps.py                                                  |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/event/forms.py                                                 |      161 |        7 |       34 |        5 |     94% |77-80, 131-132, 145, 240->exit, 295-296, 359->exit |
| src/pretalx/event/models/event.py                                          |      538 |       30 |      112 |       10 |     93% |483, 488, 534, 537, 678-680, 709->723, 741, 745-756, 778-779, 819, 831-840, 973, 988->991 |
| src/pretalx/event/models/organiser.py                                      |      117 |        8 |       18 |        6 |     90% |48, 55, 69, 77, 255, 263, 270, 308 |
| src/pretalx/event/rules.py                                                 |       51 |        0 |       12 |        0 |    100% |           |
| src/pretalx/event/services.py                                              |       34 |        3 |       10 |        1 |     91% |     62-66 |
| src/pretalx/event/stages.py                                                |       39 |        0 |       10 |        0 |    100% |           |
| src/pretalx/event/utils.py                                                 |        7 |        0 |        2 |        0 |    100% |           |
| src/pretalx/mail/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/context.py                                                |       67 |        2 |       32 |        2 |     96% |    63, 76 |
| src/pretalx/mail/default\_templates.py                                     |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/models.py                                                 |      247 |       11 |       62 |        7 |     94% |41, 249-265, 267, 274, 432->434, 456, 510-513 |
| src/pretalx/mail/placeholders.py                                           |       40 |        3 |        2 |        0 |     93% |16, 28, 50 |
| src/pretalx/mail/signals.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/tasks.py                                                  |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/context\_processors.py                                    |       42 |        0 |       18 |        1 |     98% |    17->14 |
| src/pretalx/orga/forms/cfp.py                                              |      313 |       55 |       82 |       21 |     77% |88->exit, 160, 162, 172-186, 205, 212, 225-271, 338->340, 341, 349, 365->exit, 374->376, 377, 400, 448-449, 514, 515->exit, 528, 530, 554, 632->635 |
| src/pretalx/orga/forms/event.py                                            |      382 |       45 |      114 |       22 |     85% |191, 216-217, 259, 271, 280->288, 290-293, 308, 314->exit, 447, 460-462, 465, 474, 647-655, 687, 705, 728-731, 745-752, 754-757, 785->787, 795-799, 912->exit, 957-960, 963, 971, 975 |
| src/pretalx/orga/forms/export.py                                           |       91 |        2 |       32 |        2 |     97% |  119, 139 |
| src/pretalx/orga/forms/mails.py                                            |      281 |       23 |       88 |       15 |     89% |35->37, 64, 71-72, 80-81, 88-89, 120, 140, 160->178, 172-173, 204, 231, 293-301, 310, 322-323, 485, 488->499, 509 |
| src/pretalx/orga/forms/review.py                                           |      272 |       27 |       74 |       12 |     86% |37, 132, 207-208, 237, 267-269, 285-291, 344, 370, 387, 408, 462, 466-467, 474->478, 480-481, 489-490, 498 |
| src/pretalx/orga/forms/schedule.py                                         |      119 |       30 |       14 |        2 |     71% |42->exit, 199, 214, 217-219, 222-224, 227-229, 232-233, 236-237, 240-241, 244-245, 248-249, 252-253, 256, 259, 262, 265, 268, 271, 274 |
| src/pretalx/orga/forms/speaker.py                                          |       45 |        4 |        2 |        1 |     89% |71, 82, 85, 91 |
| src/pretalx/orga/forms/submission.py                                       |      175 |       17 |       74 |       15 |     86% |68-70, 110->112, 115, 118->126, 138, 142, 153, 162, 169, 178, 187->189, 196, 220-222, 278, 364-365 |
| src/pretalx/orga/forms/widgets.py                                          |       47 |        2 |        0 |        0 |     96% |     93-94 |
| src/pretalx/orga/permissions.py                                            |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/phrases.py                                                |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/receivers.py                                              |       14 |        2 |        4 |        2 |     78% |    17, 29 |
| src/pretalx/orga/rules.py                                                  |        8 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/signals.py                                                |       28 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/cfp.py                                             |       91 |        5 |       10 |        5 |     90% |64, 84, 240, 250, 252 |
| src/pretalx/orga/tables/feedback.py                                        |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/tables/mail.py                                            |       43 |        3 |        2 |        0 |     89% |   114-116 |
| src/pretalx/orga/tables/organiser.py                                       |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/schedule.py                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/speaker.py                                         |       58 |        3 |        4 |        2 |     92% |42, 45, 51 |
| src/pretalx/orga/tables/submission.py                                      |      168 |       36 |       54 |        6 |     71% |119->121, 130, 158, 161, 167, 237, 239, 248->250, 277-279, 320, 331-335, 338-372 |
| src/pretalx/orga/templatetags/formsets.py                                  |       15 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/orga\_edit\_link.py                          |        9 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/templatetags/platform\_icons.py                           |        8 |        1 |        0 |        0 |     88% |        16 |
| src/pretalx/orga/templatetags/querystring.py                               |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/review\_score.py                             |       17 |        1 |        8 |        1 |     92% |        25 |
| src/pretalx/orga/utils/i18n.py                                             |       39 |        5 |       12 |        2 |     82% |183-184, 210-212 |
| src/pretalx/orga/views/auth.py                                             |       63 |        2 |        8 |        2 |     94% |    46, 58 |
| src/pretalx/orga/views/cards.py                                            |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/views/cfp.py                                              |      727 |       63 |      208 |       42 |     88% |98, 101, 112-113, 117->121, 161, 169, 193, 197, 200->194, 222, 229, 231, 233, 235-237, 267-273, 291, 301->304, 305, 309-317, 363, 372, 409->403, 411->403, 484, 549, 609-610, 693, 694->696, 698->700, 700->703, 764, 777, 825, 827, 886->888, 930-935, 954-955, 1002->1001, 1014-1015, 1044-1045, 1048, 1052, 1070, 1089, 1138, 1151, 1190-1196 |
| src/pretalx/orga/views/dashboard.py                                        |      162 |       28 |       46 |        9 |     78% |32-44, 80, 109-115, 137-138, 157-168, 220, 237-240, 286-287, 296->308, 353-354, 363-370 |
| src/pretalx/orga/views/event.py                                            |      432 |       28 |      110 |       25 |     89% |157-158, 202, 271, 320, 360, 362->366, 390, 395->393, 410, 418, 422, 428, 458, 462->460, 464, 474-475, 478-482, 485, 590-596, 664, 684, 707-708, 732->731, 735->737, 738, 779->784 |
| src/pretalx/orga/views/mails.py                                            |      387 |       52 |       80 |       16 |     83% |60-61, 190, 219-221, 224-226, 233-235, 286-292, 368-370, 407->415, 411, 437, 442-443, 470, 494, 500-546, 572-574, 589, 595, 613, 676, 695-704 |
| src/pretalx/orga/views/organiser.py                                        |      312 |       27 |       58 |        8 |     85% |120-122, 143-144, 159-160, 295-296, 337, 384, 397, 399-415, 479-481 |
| src/pretalx/orga/views/person.py                                           |      120 |       20 |       30 |        5 |     81% |77-86, 90-96, 98-106, 155, 164, 180-181 |
| src/pretalx/orga/views/plugins.py                                          |       56 |        0 |       14 |        0 |    100% |           |
| src/pretalx/orga/views/review.py                                           |      562 |       49 |      132 |       21 |     88% |95, 98-101, 103-106, 256->258, 258->264, 299->exit, 320-321, 323-329, 372->374, 379, 385-390, 406, 448-461, 471, 483-484, 494->496, 502-503, 554-555, 566-567, 578->590, 592, 741->747, 785-786, 961-962, 1023-1034, 1049, 1076-1077 |
| src/pretalx/orga/views/schedule.py                                         |      300 |       29 |       52 |        9 |     86% |52->59, 121-122, 165-168, 316, 317->320, 329, 359, 382, 394, 404, 414-445, 463, 505, 570-577 |
| src/pretalx/orga/views/speaker.py                                          |      192 |       11 |       22 |        5 |     92% |104-114, 116-119, 123, 224, 298, 361-362 |
| src/pretalx/orga/views/submission.py                                       |      691 |       36 |      118 |       21 |     92% |208-212, 232-234, 237, 254-260, 349->357, 434, 442, 465, 553, 556->550, 593, 616->626, 627, 634->646, 644->646, 705, 757->exit, 759, 841-842, 875->885, 921, 972, 999, 1261, 1265, 1269, 1276-1282, 1305-1306, 1308-1309 |
| src/pretalx/orga/views/typeahead.py                                        |       59 |       16 |       16 |        5 |     64% |37, 46, 55, 96-101, 106, 111-123, 146, 185-188 |
| src/pretalx/person/apps.py                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/exporters.py                                            |       25 |        1 |        4 |        1 |     93% |        38 |
| src/pretalx/person/forms/auth.py                                           |       43 |        2 |       10 |        2 |     92% |    41, 48 |
| src/pretalx/person/forms/auth\_token.py                                    |       42 |       17 |       10 |        0 |     52% |59-61, 72-91 |
| src/pretalx/person/forms/information.py                                    |       21 |        1 |        2 |        1 |     91% |        18 |
| src/pretalx/person/forms/profile.py                                        |      191 |       14 |       66 |       12 |     88% |66->68, 142->exit, 163->165, 175->181, 186->189, 210->exit, 217, 233-239, 242-243, 296->exit, 314, 342, 351, 354-355 |
| src/pretalx/person/forms/user.py                                           |      108 |       10 |       26 |        4 |     90% |99-102, 110, 113-114, 143, 155, 201 |
| src/pretalx/person/models/auth\_token.py                                   |       73 |       11 |       20 |        0 |     82% |99, 102, 144-153 |
| src/pretalx/person/models/information.py                                   |       33 |        0 |        2 |        1 |     97% |    20->22 |
| src/pretalx/person/models/picture.py                                       |       57 |        2 |       20 |        4 |     92% |46->49, 73->exit, 78, 92 |
| src/pretalx/person/models/preferences.py                                   |       41 |        5 |       18 |        3 |     83% |40-45, 83, 99->102 |
| src/pretalx/person/models/profile.py                                       |       61 |        5 |        4 |        2 |     89% |122, 129, 156-157, 163, 169->179 |
| src/pretalx/person/models/user.py                                          |      257 |       18 |       56 |        8 |     89% |40, 86, 220-223, 233->236, 241, 256, 275, 353-358, 424, 448-450, 475->488 |
| src/pretalx/person/rules.py                                                |       32 |        2 |       10 |        2 |     90% |    44, 46 |
| src/pretalx/person/services.py                                             |        8 |        0 |        2 |        1 |     90% |    20->22 |
| src/pretalx/person/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/tasks.py                                                |       18 |        0 |        2 |        0 |    100% |           |
| src/pretalx/schedule/apps.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/ascii.py                                              |      127 |       30 |       54 |        8 |     71% |65->68, 71->74, 76-80, 92-97, 98->exit, 103-115, 141, 144-165, 175 |
| src/pretalx/schedule/exporters.py                                          |      119 |        4 |       22 |        0 |     96% |   333-339 |
| src/pretalx/schedule/forms.py                                              |       54 |        0 |        8 |        1 |     98% |    63->66 |
| src/pretalx/schedule/ical.py                                               |       32 |        2 |        4 |        0 |     94% |     24-25 |
| src/pretalx/schedule/models/availability.py                                |       86 |        1 |       30 |        1 |     98% |55, 76->79 |
| src/pretalx/schedule/models/room.py                                        |       47 |        3 |        4 |        2 |     90% |94, 101, 104 |
| src/pretalx/schedule/models/schedule.py                                    |      191 |       22 |       62 |        3 |     88% |143-184, 327, 371->373, 473 |
| src/pretalx/schedule/models/slot.py                                        |      126 |        5 |       20 |        2 |     94% |208-215, 226 |
| src/pretalx/schedule/notifications.py                                      |       24 |        0 |        8 |        0 |    100% |           |
| src/pretalx/schedule/phrases.py                                            |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/services.py                                           |      222 |        9 |       86 |       12 |     92% |72->74, 77->79, 79->81, 81->83, 83->76, 122-127, 131->129, 133->135, 145->137, 148->150, 150->153, 346, 437-438 |
| src/pretalx/schedule/signals.py                                            |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/tasks.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/utils.py                                              |       14 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/apps.py                                             |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/cards.py                                            |       83 |        1 |        8 |        1 |     98% |        34 |
| src/pretalx/submission/exporters.py                                        |       43 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/forms/comment.py                                    |       18 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/forms/feedback.py                                   |       25 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/forms/question.py                                   |       68 |        0 |       30 |        2 |     98% |87->exit, 109->108 |
| src/pretalx/submission/forms/resource.py                                   |       25 |        2 |        6 |        2 |     87% |    31, 35 |
| src/pretalx/submission/forms/submission.py                                 |      250 |       29 |      108 |       15 |     85% |114, 159, 173, 178->exit, 183, 223, 227-228, 231, 238-245, 268->270, 393, 424, 478-491, 493-496, 517-520, 525 |
| src/pretalx/submission/forms/tag.py                                        |       21 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/icons.py                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/access\_code.py                              |       55 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/models/cfp.py                                       |       82 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/models/comment.py                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/feedback.py                                  |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/question.py                                  |      272 |       23 |       66 |        7 |     86% |41->44, 377, 381-382, 400-404, 410, 450->453, 514-520, 591, 600-602, 633->640, 635, 638-639 |
| src/pretalx/submission/models/resource.py                                  |       39 |        0 |        8 |        2 |     96% |59->exit, 66->exit |
| src/pretalx/submission/models/review.py                                    |      125 |       11 |       26 |        7 |     85% |55-56, 59->exit, 72, 76-78, 95, 98->102, 103, 108, 185, 294 |
| src/pretalx/submission/models/submission.py                                |      523 |       35 |      128 |       16 |     91% |392-394, 469, 511->531, 519, 523-525, 538-539, 633->639, 650-651, 728->exit, 735, 751-753, 756, 824-840, 895, 926, 979-982, 1074->1078, 1102->exit, 1121-1133, 1150->exit, 1202 |
| src/pretalx/submission/models/tag.py                                       |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/track.py                                     |       39 |        1 |        0 |        0 |     97% |        81 |
| src/pretalx/submission/models/type.py                                      |       44 |        1 |        4 |        1 |     96% |        20 |
| src/pretalx/submission/phrases.py                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/rules.py                                            |      190 |       13 |       58 |        6 |     92% |13-14, 30-31, 81, 176-177, 191, 198, 227, 239, 258, 309 |
| src/pretalx/submission/signals.py                                          |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/tasks.py                                            |       88 |       13 |       20 |        4 |     84% |32-33, 37, 75, 82-85, 95-96, 103-105 |
| src/tests/agenda/test\_agenda\_permissions.py                              |       22 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_schedule\_export.py                         |      352 |        0 |        8 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_widget.py                                   |       41 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_featured.py                           |       58 |        0 |        4 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_feedback.py                           |       68 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_schedule.py                           |      249 |        0 |       24 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_talks.py                              |      200 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_widget.py                             |       42 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_access\_code.py                                   |      211 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_answers.py                                        |      139 |        0 |        4 |        0 |    100% |           |
| src/tests/api/test\_api\_events.py                                         |       49 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_feedback.py                                       |      178 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_mail.py                                           |      114 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_questions.py                                      |      479 |        0 |        8 |        0 |    100% |           |
| src/tests/api/test\_api\_reviews.py                                        |      381 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_rooms.py                                          |      211 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_root.py                                           |       13 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_schedule.py                                       |      499 |        0 |        8 |        0 |    100% |           |
| src/tests/api/test\_api\_speaker\_information.py                           |      145 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_speakers.py                                       |      307 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_submissions.py                                    |      933 |        0 |       10 |        0 |    100% |           |
| src/tests/api/test\_api\_teams.py                                          |      213 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_upload.py                                         |       30 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/test\_cfp\_flow.py                                           |      165 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_auth.py                                     |      139 |        0 |        2 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_base.py                                     |       70 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_user.py                                     |      871 |        0 |       24 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_view\_flow.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_wizard.py                                   |      641 |        0 |       34 |        0 |    100% |           |
| src/tests/common/forms/test\_cfp\_forms\_utils.py                          |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/forms/test\_cfp\_forms\_validators.py                     |       13 |        0 |        2 |        0 |    100% |           |
| src/tests/common/forms/test\_common\_form\_widgets.py                      |       82 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_log.py                                         |       43 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_middleware.py                                  |       68 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_serialize.py                                   |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_cache.py                                    |       39 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_checks.py                                   |       16 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_console.py                                  |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_css.py                                      |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_exporter.py                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_forms\_utils.py                             |        9 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_mail.py                                     |       62 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_management\_commands.py                     |       76 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_middleware\_domains.py                      |       12 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_models\_log.py                              |       76 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_plugins.py                                  |       24 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_signals.py                                  |       28 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_templatetags.py                             |       38 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_ui.py                                       |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_utils.py                                    |       24 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_diff\_utils.py                                      |       59 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_update\_check.py                                    |      117 |        0 |        0 |        0 |    100% |           |
| src/tests/common/views/test\_shortlink.py                                  |       88 |        0 |        0 |        0 |    100% |           |
| src/tests/conftest.py                                                      |      544 |        0 |       12 |        0 |    100% |           |
| src/tests/dummy\_app.py                                                    |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/dummy\_signals.py                                                |       52 |        0 |        8 |        0 |    100% |           |
| src/tests/event/test\_event\_model.py                                      |      180 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_services.py                                   |       61 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_stages.py                                     |       24 |        0 |        6 |        0 |    100% |           |
| src/tests/event/test\_event\_utils.py                                      |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/mail/test\_mail\_models.py                                       |      155 |        0 |        4 |        0 |    100% |           |
| src/tests/orga/test\_orga\_access.py                                       |       73 |        0 |       12 |        0 |    100% |           |
| src/tests/orga/test\_orga\_auth.py                                         |      145 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_forms.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_permissions.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_utils.py                                        |        6 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_templatetags.py                                       |       18 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_tables.py                                 |      284 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_admin.py                           |      104 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_cfp.py                             |      810 |        0 |       10 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_dashboard.py                       |      173 |        0 |       52 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_event.py                           |      480 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_mail.py                            |      509 |        0 |       18 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_organiser.py                       |      340 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_person.py                          |       44 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_review.py                          |      486 |        0 |        8 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_schedule.py                        |      346 |        0 |        8 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_speaker.py                         |      293 |        0 |        6 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission.py                      |      782 |        0 |       16 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission\_cards.py               |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_auth\_token\_model.py                               |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_information\_model.py                               |        7 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_person\_permissions.py                              |       10 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_profile\_picture\_field.py                          |      230 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_tasks.py                                            |       54 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_user\_model.py                                      |       68 |        0 |        0 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_availability.py                         |       57 |        0 |        4 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_exporters.py                            |       28 |        0 |        0 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_forms.py                                |      105 |        0 |       10 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_model.py                                |      199 |        0 |        2 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_models\_slot.py                         |       98 |        0 |        6 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_utils.py                                |       25 |        0 |        2 |        0 |    100% |           |
| src/tests/services/test\_documentation.py                                  |       37 |        0 |       12 |        0 |    100% |           |
| src/tests/services/test\_models.py                                         |        8 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_access\_code\_model.py                          |        7 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_cfp\_model.py                                   |       15 |        0 |        2 |        0 |    100% |           |
| src/tests/submission/test\_question\_model.py                              |      150 |        0 |       10 |        0 |    100% |           |
| src/tests/submission/test\_review\_model.py                                |       19 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_model.py                            |      297 |        0 |        2 |        0 |    100% |           |
| src/tests/submission/test\_submission\_permissions.py                      |       47 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_tasks.py                            |       98 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_type\_model.py                      |       21 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                                                                  | **36561** | **1836** | **5656** |  **763** | **93%** |           |


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