# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/pretalx/agenda/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/context\_processors.py                                  |        2 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/management/commands/export\_schedule\_html.py           |      167 |        3 |       44 |        3 |     97% |64->63, 72->66, 89->88, 258-260 |
| src/pretalx/agenda/phrases.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/recording.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/rules.py                                                |       31 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/tasks.py                                                |       33 |        0 |        8 |        2 |     95% |42->exit, 44->exit |
| src/pretalx/agenda/views/featured.py                                       |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/feed.py                                           |       34 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/schedule.py                                       |      136 |        2 |       34 |        1 |     98% |   64, 144 |
| src/pretalx/agenda/views/speaker.py                                        |       90 |        8 |       18 |        3 |     86% |84-90, 126, 131-132, 144->exit |
| src/pretalx/agenda/views/talk.py                                           |      155 |        3 |       18 |        3 |     95% |73->72, 79->72, 151-154 |
| src/pretalx/agenda/views/utils.py                                          |       51 |        6 |       22 |        4 |     86% |21, 59, 61, 65-69, 77->79 |
| src/pretalx/agenda/views/widget.py                                         |       84 |        6 |       28 |        3 |     92% |48, 91-94, 109 |
| src/pretalx/api/apps.py                                                    |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/documentation.py                                           |       26 |        0 |        4 |        1 |     97% |    11->26 |
| src/pretalx/api/exceptions.py                                              |        9 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/filters/answer.py                                          |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/feedback.py                                        |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/review.py                                          |       27 |        0 |        2 |        1 |     97% |  65->exit |
| src/pretalx/api/filters/schedule.py                                        |       23 |        0 |        4 |        1 |     96% |  41->exit |
| src/pretalx/api/filters/submission.py                                      |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/pagination.py                                              |       23 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/permissions.py                                             |       33 |        0 |       16 |        1 |     98% |    50->57 |
| src/pretalx/api/serializers/access\_code.py                                |       72 |        2 |       20 |        0 |     98% |     51-52 |
| src/pretalx/api/serializers/availability.py                                |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/event.py                                       |       23 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/feedback.py                                    |       36 |        1 |        6 |        1 |     95% |        44 |
| src/pretalx/api/serializers/fields.py                                      |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/log.py                                         |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/serializers/mail.py                                        |       29 |        2 |        4 |        0 |     94% |     36-37 |
| src/pretalx/api/serializers/mixins.py                                      |       38 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/question.py                                    |      126 |        7 |       32 |        2 |     91% |280-289, 322 |
| src/pretalx/api/serializers/review.py                                      |       74 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/room.py                                        |       30 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/schedule.py                                    |       71 |        1 |       12 |        1 |     98% |        39 |
| src/pretalx/api/serializers/speaker.py                                     |       91 |        4 |       28 |        4 |     93% |36, 76, 116, 142 |
| src/pretalx/api/serializers/speaker\_information.py                        |       35 |        1 |        6 |        1 |     95% |        63 |
| src/pretalx/api/serializers/submission.py                                  |      235 |       21 |       74 |       15 |     88% |121, 133, 159, 210, 224, 371-377, 383->385, 386, 391, 393-395, 404-405, 417, 419-420, 422, 424, 426 |
| src/pretalx/api/serializers/team.py                                        |       49 |        0 |        8 |        0 |    100% |           |
| src/pretalx/api/shims.py                                                   |       18 |       18 |        0 |        0 |      0% |     11-35 |
| src/pretalx/api/versions.py                                                |       30 |        1 |       10 |        1 |     95% |        35 |
| src/pretalx/api/views/access\_code.py                                      |       25 |        2 |        0 |        0 |     92% |     61-62 |
| src/pretalx/api/views/event.py                                             |       24 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/feedback.py                                          |       37 |        1 |       10 |        1 |     96% |        75 |
| src/pretalx/api/views/mail.py                                              |       15 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/mixins.py                                            |       77 |        3 |       16 |        6 |     90% |45->47, 62->65, 68->71, 72->76, 105, 115-118 |
| src/pretalx/api/views/question.py                                          |      104 |        9 |       16 |        3 |     88% |106-110, 157, 170-171, 238-239, 269->281 |
| src/pretalx/api/views/review.py                                            |       45 |        1 |       12 |        1 |     96% |       115 |
| src/pretalx/api/views/room.py                                              |       35 |        2 |        4 |        0 |     95% |     68-69 |
| src/pretalx/api/views/root.py                                              |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/schedule.py                                          |      129 |        8 |       36 |        8 |     90% |80, 90, 114, 148, 222, 300, 316, 322 |
| src/pretalx/api/views/speaker.py                                           |       57 |        1 |       12 |        1 |     97% |       150 |
| src/pretalx/api/views/speaker\_information.py                              |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/submission.py                                        |      245 |       18 |       30 |        5 |     91% |247, 268, 272, 294, 307-308, 316-317, 325-326, 334-335, 343-344, 398-401 |
| src/pretalx/api/views/team.py                                              |       90 |        4 |        6 |        0 |     96% |81-82, 187-188 |
| src/pretalx/api/views/upload.py                                            |       37 |        5 |        8 |        2 |     84% | 63, 74-77 |
| src/pretalx/cfp/apps.py                                                    |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/flow.py                                                    |      651 |       14 |      212 |       16 |     96% |181, 260, 436->430, 485, 545, 547, 582->595, 584->583, 586-587, 630-632, 795->exit, 885, 899, 905->908, 966, 970, 986->988, 988->998 |
| src/pretalx/cfp/forms/auth.py                                              |       26 |        0 |        2 |        0 |    100% |           |
| src/pretalx/cfp/forms/cfp.py                                               |       30 |        2 |       18 |        1 |     94% |    47, 53 |
| src/pretalx/cfp/forms/submissions.py                                       |       43 |        4 |       10 |        1 |     87% |     53-56 |
| src/pretalx/cfp/phrases.py                                                 |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/signals.py                                                 |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/auth.py                                              |       91 |       25 |       10 |        1 |     66% |47, 51, 108, 112-138 |
| src/pretalx/cfp/views/event.py                                             |       57 |        6 |       10 |        3 |     84% |30, 62, 82, 92-95 |
| src/pretalx/cfp/views/locale.py                                            |       20 |        1 |        6 |        2 |     88% |21->40, 32 |
| src/pretalx/cfp/views/robots.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/user.py                                              |      365 |       18 |       66 |       11 |     93% |140, 162, 234-236, 260, 303-305, 378, 383, 386->380, 426-427, 468->472, 476, 488, 490, 507->509, 619-620 |
| src/pretalx/cfp/views/wizard.py                                            |       76 |        1 |       36 |        1 |     98% |       102 |
| src/pretalx/common/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/auth.py                                                 |       20 |        3 |        4 |        1 |     83% | 31-32, 35 |
| src/pretalx/common/cache.py                                                |       58 |        4 |       10 |        0 |     94% |56, 59, 62, 65 |
| src/pretalx/common/checks.py                                               |       66 |       40 |       30 |        3 |     32% |16-54, 59-69, 74-85, 91, 96-97, 106, 128-139, 144-167 |
| src/pretalx/common/context\_processors.py                                  |       57 |        0 |       14 |        0 |    100% |           |
| src/pretalx/common/db.py                                                   |       10 |        3 |        0 |        0 |     70% |     19-21 |
| src/pretalx/common/diff\_utils.py                                          |       45 |        2 |       18 |        3 |     92% |58, 60, 84->77 |
| src/pretalx/common/exceptions.py                                           |       59 |       37 |       20 |        0 |     28% |55-60, 63-69, 72-80, 85-87, 90, 93-102, 109-111 |
| src/pretalx/common/exporter.py                                             |       64 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/formats/en/formats.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/fields.py                                         |      279 |       17 |      102 |       16 |     91% |70, 96, 118, 196-197, 211->exit, 213, 220, 231, 248->251, 251->exit, 294, 350->exit, 355, 368-369, 395-396, 398-399, 453->451, 479 |
| src/pretalx/common/forms/forms.py                                          |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/mixins.py                                         |      308 |       31 |      150 |       30 |     86% |67->61, 114, 160, 250->255, 252, 254, 265-274, 299->304, 395->397, 397->399, 409->411, 411->413, 416->418, 418->420, 434->436, 436->438, 439, 482, 484->503, 490, 495, 514->516, 521-522, 534->536, 562-572, 575, 578-584, 586, 587->557, 591-593, 609->599 |
| src/pretalx/common/forms/renderers.py                                      |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/tables.py                                         |       40 |        1 |       16 |        2 |     95% |61, 100->105 |
| src/pretalx/common/forms/validators.py                                     |       50 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/forms/widgets.py                                        |      296 |        5 |       42 |        5 |     97% |256, 289, 410, 560, 571 |
| src/pretalx/common/image.py                                                |       98 |       29 |       36 |        7 |     63% |30-72, 95, 97, 110, 124->128, 128->exit, 149, 152, 176 |
| src/pretalx/common/language.py                                             |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/log\_display.py                                         |       86 |       10 |       38 |        6 |     87% |171, 188, 197-202, 204-206, 243, 246 |
| src/pretalx/common/mail.py                                                 |       94 |       18 |       26 |        4 |     78% |68-70, 79-81, 112, 165-167, 179-185, 190 |
| src/pretalx/common/management/commands/create\_test\_event.py              |      179 |        5 |       54 |        2 |     96% |150->exit, 155, 164-167 |
| src/pretalx/common/management/commands/devserver.py                        |       16 |       16 |        4 |        0 |      0% |     10-39 |
| src/pretalx/common/management/commands/init.py                             |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/makemessages.py                     |       49 |        6 |       18 |        3 |     84% |47-48, 56, 70-72 |
| src/pretalx/common/management/commands/makemigrations.py                   |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/management/commands/migrate.py                          |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/management/commands/move\_event.py                      |       29 |        0 |        4 |        1 |     97% |  39->exit |
| src/pretalx/common/management/commands/rebuild.py                          |       35 |        3 |        2 |        1 |     89% | 49-50, 68 |
| src/pretalx/common/management/commands/runperiodic.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/sendtestemail.py                    |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/management/commands/shell.py                            |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/spectacular.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/update\_translation\_percentages.py |       31 |       31 |        6 |        0 |      0% |      4-41 |
| src/pretalx/common/middleware/domains.py                                   |      123 |       14 |       44 |        7 |     84% |45, 79->84, 85, 98-116, 166->172, 172->188, 208-209, 233-238 |
| src/pretalx/common/middleware/event.py                                     |      123 |       12 |       48 |        4 |     87% |103-105, 140-144, 185-193, 207->exit, 219->exit |
| src/pretalx/common/models/fields.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/models/file.py                                          |       23 |        1 |        2 |        1 |     92% |        46 |
| src/pretalx/common/models/log.py                                           |       71 |        7 |       28 |        8 |     85% |83, 89->93, 98, 101, 106, 110->125, 115->125, 118, 123-124 |
| src/pretalx/common/models/mixins.py                                        |      206 |       27 |       84 |        6 |     84% |47, 128, 307, 324->322, 348, 351->exit, 356-359, 378-381, 384, 387, 390, 393, 397, 400-410 |
| src/pretalx/common/models/transaction.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/plugins.py                                              |       30 |        0 |        8 |        1 |     97% |    63->69 |
| src/pretalx/common/settings/config.py                                      |       23 |        1 |        2 |        1 |     92% |       172 |
| src/pretalx/common/signals.py                                              |      118 |       14 |       34 |        3 |     89% |38, 80, 175, 181-186, 190-191, 196-198 |
| src/pretalx/common/tables.py                                               |      405 |       50 |      168 |       26 |     85% |63, 65->67, 78-79, 82-83, 138->136, 143->145, 167, 211-212, 256, 263, 289, 292-294, 297->300, 304-310, 324, 398->402, 440-442, 475, 480, 493, 499, 503-506, 573, 584-586, 640, 651->653, 656-657, 675->677, 705-707, 713, 718, 728-730, 733-734 |
| src/pretalx/common/tasks.py                                                |       40 |        4 |       14 |        5 |     83% |28, 57, 62, 68, 71->exit |
| src/pretalx/common/templatetags/copyable.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/templatetags/datetimerange.py                           |       28 |        5 |        6 |        3 |     76% |31, 33, 46-48 |
| src/pretalx/common/templatetags/event\_tags.py                             |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/filesize.py                                |       13 |        3 |        4 |        1 |     76% | 13-14, 19 |
| src/pretalx/common/templatetags/form\_media.py                             |       44 |        6 |       28 |        2 |     81% | 39, 58-67 |
| src/pretalx/common/templatetags/history\_sidebar.py                        |       77 |       41 |       26 |        8 |     43% |16-24, 32->36, 49-51, 55-60, 72, 74, 84-85, 87-88, 90-91, 93-95, 97-120 |
| src/pretalx/common/templatetags/html\_signal.py                            |       12 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/templatetags/phrases.py                                 |       11 |        1 |        2 |        1 |     85% |        20 |
| src/pretalx/common/templatetags/rich\_text.py                              |       60 |        1 |        8 |        0 |     99% |       204 |
| src/pretalx/common/templatetags/safelink.py                                |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/thumbnail.py                               |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/times.py                                   |       13 |        0 |        6 |        0 |    100% |           |
| src/pretalx/common/templatetags/vite.py                                    |       56 |       28 |       24 |        5 |     41% |20-24, 32, 40-58, 69, 74-84, 91 |
| src/pretalx/common/templatetags/xmlescape.py                               |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/text/console.py                                         |       66 |       24 |       18 |        3 |     65% |45-46, 52-53, 67-68, 85, 91-127 |
| src/pretalx/common/text/css.py                                             |       27 |        0 |       12 |        0 |    100% |           |
| src/pretalx/common/text/daterange.py                                       |       33 |        0 |       18 |        0 |    100% |           |
| src/pretalx/common/text/path.py                                            |       21 |        4 |        6 |        2 |     70% |32->40, 35-38 |
| src/pretalx/common/text/phrases.py                                         |       59 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/text/serialize.py                                       |       27 |        1 |        8 |        1 |     94% |        40 |
| src/pretalx/common/text/xml.py                                             |       12 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/ui.py                                                   |       52 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/update\_check.py                                        |       66 |        0 |       20 |        0 |    100% |           |
| src/pretalx/common/views/cache.py                                          |       61 |       10 |       30 |       13 |     75% |20, 26, 53, 76, 78, 84->87, 104->107, 113, 115, 118, 124, 130->136, 137 |
| src/pretalx/common/views/errors.py                                         |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/views/generic.py                                        |      474 |       57 |      132 |       22 |     85% |72, 74, 75->68, 88-89, 93-97, 144->147, 183, 196-197, 225-226, 307-308, 328, 331, 338-340, 376->exit, 386-388, 425, 428, 431-444, 462->464, 467-469, 512->515, 522->531, 528->531, 636->644, 645-666, 680->688, 692, 714, 725, 750->752, 762 |
| src/pretalx/common/views/helpers.py                                        |        8 |        1 |        0 |        0 |     88% |        31 |
| src/pretalx/common/views/mixins.py                                         |      319 |       81 |      114 |       14 |     71% |41, 45, 58-82, 92-93, 109-116, 133, 169-170, 184-188, 193, 203-204, 225, 251, 269, 283-301, 308, 342-346, 373, 388-391, 427, 432-439, 470-471, 495, 508-510 |
| src/pretalx/common/views/redirect.py                                       |       26 |       11 |        6 |        0 |     47% |13-23, 33-43 |
| src/pretalx/common/views/shortlink.py                                      |       30 |        0 |       18 |        0 |    100% |           |
| src/pretalx/event/apps.py                                                  |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/event/forms.py                                                 |      161 |        7 |       34 |        5 |     94% |77-80, 133-134, 147, 242->exit, 297-298, 364->exit |
| src/pretalx/event/models/event.py                                          |      544 |       31 |      118 |       11 |     92% |485, 490, 536, 539, 691-693, 722->736, 754, 758-769, 791-792, 800, 832, 844-853, 987, 1002->1005 |
| src/pretalx/event/models/organiser.py                                      |      116 |        8 |       18 |        6 |     90% |47, 54, 68, 76, 257, 265, 272, 314 |
| src/pretalx/event/rules.py                                                 |       51 |        0 |       12 |        0 |    100% |           |
| src/pretalx/event/services.py                                              |       34 |        3 |       10 |        1 |     91% |     62-66 |
| src/pretalx/event/stages.py                                                |       39 |        0 |       10 |        0 |    100% |           |
| src/pretalx/event/utils.py                                                 |        7 |        0 |        2 |        0 |    100% |           |
| src/pretalx/mail/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/context.py                                                |       68 |        2 |       32 |        2 |     96% |    63, 76 |
| src/pretalx/mail/default\_templates.py                                     |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/models.py                                                 |      246 |       11 |       62 |        7 |     94% |40, 253-269, 271, 278, 443->445, 467, 524-527 |
| src/pretalx/mail/placeholders.py                                           |       40 |        3 |        2 |        0 |     93% |16, 28, 50 |
| src/pretalx/mail/signals.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/tasks.py                                                  |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/context\_processors.py                                    |       42 |        0 |       18 |        1 |     98% |    17->14 |
| src/pretalx/orga/forms/cfp.py                                              |      315 |       57 |       86 |       21 |     76% |89->exit, 164, 166, 176-190, 209, 216, 229-275, 342->344, 345, 353, 369->exit, 378->380, 381, 406, 454-455, 523, 524->exit, 537, 539, 563, 644->647 |
| src/pretalx/orga/forms/event.py                                            |      383 |       45 |      114 |       22 |     85% |194, 220-221, 261, 273, 282->290, 292-295, 310, 316->exit, 452, 465-467, 470, 479, 656-664, 696, 714, 737-740, 754-761, 763-766, 796->798, 806-810, 927->exit, 972-975, 978, 986, 990 |
| src/pretalx/orga/forms/export.py                                           |       91 |        2 |       32 |        2 |     97% |  125, 145 |
| src/pretalx/orga/forms/mails.py                                            |      281 |       23 |       88 |       15 |     89% |35->37, 64, 71-72, 80-81, 88-89, 120, 140, 160->178, 172-173, 204, 239, 301-309, 318, 330-331, 501, 504->515, 529 |
| src/pretalx/orga/forms/review.py                                           |      271 |       27 |       74 |       12 |     86% |36, 137, 212-213, 244, 274-276, 292-298, 358, 384, 401, 423, 480, 485-486, 491->495, 497-498, 506-507, 515 |
| src/pretalx/orga/forms/schedule.py                                         |      119 |       30 |       14 |        2 |     71% |42->exit, 205, 220, 223-225, 228-230, 233-235, 238-239, 242-243, 246-247, 250-251, 254-255, 258-259, 262, 265, 268, 271, 274, 277, 280 |
| src/pretalx/orga/forms/speaker.py                                          |       45 |        4 |        2 |        1 |     89% |75, 86, 89, 95 |
| src/pretalx/orga/forms/submission.py                                       |      175 |       17 |       74 |       15 |     86% |68-70, 110->112, 115, 118->126, 138, 142, 153, 162, 169, 178, 187->189, 196, 220-222, 278, 369-370 |
| src/pretalx/orga/forms/widgets.py                                          |       47 |        2 |        0 |        0 |     96% |     96-97 |
| src/pretalx/orga/permissions.py                                            |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/phrases.py                                                |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/receivers.py                                              |       14 |        2 |        4 |        2 |     78% |    17, 29 |
| src/pretalx/orga/rules.py                                                  |        8 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/signals.py                                                |       28 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/cfp.py                                             |       91 |        5 |       10 |        5 |     90% |72, 96, 266, 276, 278 |
| src/pretalx/orga/tables/feedback.py                                        |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/tables/mail.py                                            |       43 |        3 |        2 |        0 |     89% |   137-139 |
| src/pretalx/orga/tables/organiser.py                                       |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/schedule.py                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/speaker.py                                         |       58 |        3 |        4 |        2 |     92% |42, 45, 51 |
| src/pretalx/orga/tables/submission.py                                      |      169 |       36 |       54 |        6 |     71% |120->122, 131, 159, 162, 168, 239, 241, 250->252, 279-281, 322, 333-337, 340-374 |
| src/pretalx/orga/templatetags/formsets.py                                  |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/orga\_edit\_link.py                          |       10 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/templatetags/platform\_icons.py                           |        9 |        1 |        2 |        1 |     82% |        16 |
| src/pretalx/orga/templatetags/querystring.py                               |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/review\_score.py                             |       17 |        1 |        8 |        1 |     92% |        25 |
| src/pretalx/orga/utils/i18n.py                                             |       39 |        5 |       12 |        2 |     82% |183-184, 210-212 |
| src/pretalx/orga/views/auth.py                                             |       63 |        2 |        8 |        2 |     94% |    46, 58 |
| src/pretalx/orga/views/cards.py                                            |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/views/cfp.py                                              |      729 |       63 |      210 |       42 |     88% |98, 101, 112-113, 117->121, 161, 169, 193, 197, 200->194, 222, 229, 231, 233, 235-237, 267-273, 291, 301->304, 305, 309-320, 366, 375, 412->406, 414->406, 490, 556, 617-618, 701, 702->704, 706->708, 708->711, 772, 785, 833, 835, 894->896, 938-943, 962-963, 1010->1009, 1022-1023, 1052-1053, 1056, 1060, 1078, 1097, 1148, 1161, 1200-1206 |
| src/pretalx/orga/views/dashboard.py                                        |      162 |       28 |       46 |        9 |     78% |32-44, 80, 109-115, 137-138, 157-168, 220, 237-240, 286-287, 296->308, 353-354, 363-370 |
| src/pretalx/orga/views/event.py                                            |      434 |       28 |      114 |       25 |     90% |156-157, 205, 274, 326, 366, 368->373, 397, 402->400, 417, 425, 429, 435, 465, 469->467, 471, 481-482, 485-489, 492, 597-603, 671, 691, 714-715, 739->738, 742->744, 745, 788->793 |
| src/pretalx/orga/views/mails.py                                            |      391 |       52 |       80 |       16 |     83% |60-61, 202, 231-233, 236-238, 245-247, 298-304, 380-382, 419->427, 423, 449, 454-455, 482, 506, 512-559, 586-588, 603, 609, 627, 694, 713-724 |
| src/pretalx/orga/views/organiser.py                                        |      313 |       27 |       58 |        8 |     85% |119-121, 142-143, 158-159, 294-295, 336, 383, 396, 398-414, 480-482 |
| src/pretalx/orga/views/person.py                                           |      120 |       20 |       30 |        5 |     81% |77-86, 90-97, 99-107, 156, 165, 181-182 |
| src/pretalx/orga/views/plugins.py                                          |       56 |        0 |       14 |        0 |    100% |           |
| src/pretalx/orga/views/review.py                                           |      562 |       49 |      132 |       21 |     88% |95, 98-101, 103-106, 258->260, 260->266, 301->exit, 322-323, 325-331, 376->378, 383, 389-394, 410, 452-465, 476, 488-489, 499->501, 507-508, 559-560, 571-572, 583->596, 598, 747->753, 791-792, 971-972, 1033-1044, 1059, 1089-1090 |
| src/pretalx/orga/views/schedule.py                                         |      300 |       29 |       52 |        9 |     86% |52->59, 121-122, 165-169, 318, 319->322, 331, 361, 384, 396, 406, 416-447, 465, 507, 572-579 |
| src/pretalx/orga/views/speaker.py                                          |      192 |       11 |       22 |        5 |     92% |104-116, 118-121, 125, 227, 301, 364-365 |
| src/pretalx/orga/views/submission.py                                       |      692 |       36 |      120 |       21 |     92% |213-217, 237-239, 242, 259-265, 354->362, 441, 449, 473, 561, 564->558, 601, 624->634, 635, 642->654, 652->654, 713, 766->exit, 768, 850-851, 884->894, 936, 987, 1014, 1276, 1280, 1284, 1291-1297, 1320-1321, 1323-1324 |
| src/pretalx/orga/views/typeahead.py                                        |       59 |       16 |       16 |        5 |     64% |45, 54, 63, 104-109, 114, 119-131, 156, 195-198 |
| src/pretalx/person/apps.py                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/exporters.py                                            |       25 |        1 |        4 |        1 |     93% |        38 |
| src/pretalx/person/forms/auth.py                                           |       43 |        2 |       10 |        2 |     92% |    41, 48 |
| src/pretalx/person/forms/auth\_token.py                                    |       43 |       17 |       10 |        0 |     53% |59-61, 74-93 |
| src/pretalx/person/forms/information.py                                    |       21 |        1 |        2 |        1 |     91% |        18 |
| src/pretalx/person/forms/profile.py                                        |      189 |       14 |       64 |       12 |     88% |75->77, 148->exit, 169->171, 181->187, 192->195, 219->exit, 226, 242-248, 251-252, 305->exit, 323, 353, 362, 365-366 |
| src/pretalx/person/forms/user.py                                           |      109 |       11 |       28 |        4 |     88% |104-108, 115, 118-119, 148, 160, 206 |
| src/pretalx/person/models/auth\_token.py                                   |       73 |       11 |       20 |        0 |     82% |103, 106, 148-157 |
| src/pretalx/person/models/information.py                                   |       33 |        0 |        2 |        1 |     97% |    20->22 |
| src/pretalx/person/models/picture.py                                       |       57 |        2 |       20 |        4 |     92% |46->49, 78->exit, 83, 97 |
| src/pretalx/person/models/preferences.py                                   |       41 |        5 |       18 |        3 |     83% |47-53, 91, 108->111 |
| src/pretalx/person/models/profile.py                                       |       62 |        5 |        4 |        2 |     89% |126, 133, 160-161, 167, 173->183 |
| src/pretalx/person/models/user.py                                          |      258 |       18 |       56 |        8 |     89% |40, 88, 226-229, 239->242, 247, 262, 281, 359-364, 430, 454-456, 481->494 |
| src/pretalx/person/rules.py                                                |       32 |        2 |       10 |        2 |     90% |    44, 46 |
| src/pretalx/person/services.py                                             |        8 |        0 |        2 |        1 |     90% |    20->22 |
| src/pretalx/person/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/tasks.py                                                |       18 |        0 |        2 |        0 |    100% |           |
| src/pretalx/schedule/apps.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/ascii.py                                              |      127 |       30 |       54 |        8 |     71% |66->69, 72->75, 77-81, 93-98, 99->exit, 104-116, 146, 149-170, 184 |
| src/pretalx/schedule/exporters.py                                          |      119 |        4 |       22 |        0 |     96% |   338-344 |
| src/pretalx/schedule/forms.py                                              |       54 |        0 |        8 |        1 |     98% |    65->68 |
| src/pretalx/schedule/ical.py                                               |       34 |        2 |        4 |        0 |     95% |     24-25 |
| src/pretalx/schedule/models/availability.py                                |       86 |        1 |       30 |        1 |     98% |55, 76->79 |
| src/pretalx/schedule/models/room.py                                        |       47 |        3 |        4 |        2 |     90% |94, 101, 104 |
| src/pretalx/schedule/models/schedule.py                                    |      191 |       22 |       62 |        3 |     88% |147-188, 339, 383->385, 485 |
| src/pretalx/schedule/models/slot.py                                        |      126 |        5 |       20 |        2 |     94% |211-218, 229 |
| src/pretalx/schedule/notifications.py                                      |       24 |        0 |        8 |        0 |    100% |           |
| src/pretalx/schedule/phrases.py                                            |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/services.py                                           |      221 |        9 |       86 |       12 |     92% |71->73, 76->78, 78->80, 80->82, 82->75, 121-126, 130->128, 132->134, 144->136, 147->149, 149->152, 341, 432-433 |
| src/pretalx/schedule/signals.py                                            |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/tasks.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/utils.py                                              |       14 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/apps.py                                             |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/cards.py                                            |       83 |        1 |        8 |        1 |     98% |        34 |
| src/pretalx/submission/exporters.py                                        |       43 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/forms/comment.py                                    |       18 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/forms/feedback.py                                   |       25 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/forms/question.py                                   |       68 |        0 |       30 |        2 |     98% |88->exit, 110->109 |
| src/pretalx/submission/forms/resource.py                                   |       25 |        2 |        6 |        2 |     87% |    31, 35 |
| src/pretalx/submission/forms/submission.py                                 |      251 |       29 |      108 |       15 |     86% |114, 159, 173, 178->exit, 183, 223, 227-228, 231, 238-245, 268->270, 394, 425, 479-492, 494-497, 518-521, 526 |
| src/pretalx/submission/forms/tag.py                                        |       21 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/icons.py                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/access\_code.py                              |       55 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/models/cfp.py                                       |       82 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/models/comment.py                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/feedback.py                                  |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/question.py                                  |      272 |       23 |       66 |        7 |     86% |41->44, 389, 393-394, 412-416, 422, 462->465, 526-532, 603, 612-614, 645->652, 647, 650-651 |
| src/pretalx/submission/models/resource.py                                  |       39 |        0 |        8 |        2 |     96% |62->exit, 69->exit |
| src/pretalx/submission/models/review.py                                    |      125 |       11 |       26 |        7 |     85% |55-56, 59->exit, 72, 76-78, 95, 98->102, 103, 108, 185, 301 |
| src/pretalx/submission/models/submission.py                                |      523 |       35 |      128 |       16 |     91% |404-406, 481, 526->546, 534, 538-540, 553-554, 654->660, 676-677, 775->exit, 782, 798-800, 803, 881-897, 952, 984, 1037-1040, 1132->1136, 1160->exit, 1179-1191, 1208->exit, 1270 |
| src/pretalx/submission/models/tag.py                                       |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/track.py                                     |       39 |        1 |        0 |        0 |     97% |        89 |
| src/pretalx/submission/models/type.py                                      |       44 |        1 |        4 |        1 |     96% |        20 |
| src/pretalx/submission/phrases.py                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/rules.py                                            |      190 |       13 |       58 |        6 |     92% |13-14, 30-31, 81, 176-177, 191, 198, 227, 239, 258, 309 |
| src/pretalx/submission/signals.py                                          |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/tasks.py                                            |       88 |       13 |       20 |        4 |     84% |32-33, 37, 75, 82-85, 95-96, 103-105 |
| src/tests/agenda/test\_agenda\_permissions.py                              |       22 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_schedule\_export.py                         |      350 |        0 |        8 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_widget.py                                   |       41 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_featured.py                           |       57 |        0 |        4 |        0 |    100% |           |
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
| src/tests/api/test\_api\_schedule.py                                       |      498 |        0 |        8 |        0 |    100% |           |
| src/tests/api/test\_api\_speaker\_information.py                           |      145 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_speakers.py                                       |      307 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_submissions.py                                    |      933 |        0 |       10 |        0 |    100% |           |
| src/tests/api/test\_api\_teams.py                                          |      213 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_upload.py                                         |       30 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/test\_cfp\_flow.py                                           |      165 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_auth.py                                     |      139 |        0 |        2 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_base.py                                     |       70 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_user.py                                     |      860 |        0 |       24 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_view\_flow.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_wizard.py                                   |      638 |        0 |       34 |        0 |    100% |           |
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
| src/tests/conftest.py                                                      |      547 |        0 |       12 |        0 |    100% |           |
| src/tests/dummy\_app.py                                                    |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/dummy\_signals.py                                                |       52 |        0 |        8 |        0 |    100% |           |
| src/tests/event/test\_event\_model.py                                      |      179 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_services.py                                   |       59 |        0 |        0 |        0 |    100% |           |
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
| src/tests/orga/views/test\_orga\_views\_cfp.py                             |      808 |        0 |       10 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_dashboard.py                       |      173 |        0 |       52 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_event.py                           |      480 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_mail.py                            |      509 |        0 |       18 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_organiser.py                       |      339 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_person.py                          |       44 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_review.py                          |      486 |        0 |        8 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_schedule.py                        |      346 |        0 |        8 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_speaker.py                         |      292 |        0 |        6 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission.py                      |      782 |        0 |       16 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission\_cards.py               |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_auth\_token\_model.py                               |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_information\_model.py                               |        7 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_person\_permissions.py                              |       10 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_profile\_picture\_field.py                          |      231 |        0 |        0 |        0 |    100% |           |
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
| **TOTAL**                                                                  | **36634** | **1859** | **5730** |  **775** | **93%** |           |


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