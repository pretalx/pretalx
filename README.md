# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/pretalx/pretalx/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/pretalx/agenda/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/context\_processors.py                                  |        2 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/management/commands/export\_schedule\_html.py           |      167 |        3 |       44 |        3 |     97% |62->61, 70->64, 87->86, 255-257 |
| src/pretalx/agenda/phrases.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/recording.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/rules.py                                                |       31 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/signals.py                                              |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/agenda/tasks.py                                                |       29 |        0 |        8 |        0 |    100% |           |
| src/pretalx/agenda/views/featured.py                                       |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/feed.py                                           |       33 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/schedule.py                                       |      136 |        2 |       34 |        1 |     98% |   64, 165 |
| src/pretalx/agenda/views/speaker.py                                        |       99 |        9 |       18 |        3 |     86% |78, 108-114, 152, 162-163 |
| src/pretalx/agenda/views/talk.py                                           |      166 |        5 |       26 |        4 |     93% |70->69, 76->69, 161-164, 175-176 |
| src/pretalx/agenda/views/utils.py                                          |       51 |        6 |       22 |        4 |     86% |21, 59, 61, 65-69, 77->79 |
| src/pretalx/agenda/views/widget.py                                         |       84 |        6 |       30 |        3 |     92% |41, 86-89, 104 |
| src/pretalx/api/apps.py                                                    |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/documentation.py                                           |       26 |        0 |        4 |        1 |     97% |    11->26 |
| src/pretalx/api/exceptions.py                                              |        9 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/filters/feedback.py                                        |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/review.py                                          |       20 |        0 |        2 |        1 |     95% |  35->exit |
| src/pretalx/api/filters/schedule.py                                        |       23 |        0 |        4 |        1 |     96% |  41->exit |
| src/pretalx/api/pagination.py                                              |       23 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/permissions.py                                             |       32 |        0 |       14 |        0 |    100% |           |
| src/pretalx/api/serializers/access\_code.py                                |       19 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/availability.py                                |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/event.py                                       |       21 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/feedback.py                                    |       35 |        1 |        6 |        1 |     95% |        43 |
| src/pretalx/api/serializers/fields.py                                      |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/log.py                                         |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/serializers/mail.py                                        |       29 |        2 |        4 |        0 |     94% |     36-37 |
| src/pretalx/api/serializers/mixins.py                                      |       38 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/question.py                                    |      122 |        6 |       32 |        1 |     92% |   268-277 |
| src/pretalx/api/serializers/review.py                                      |       74 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/room.py                                        |       30 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/schedule.py                                    |       71 |        1 |       12 |        1 |     98% |        38 |
| src/pretalx/api/serializers/speaker.py                                     |       90 |        7 |       26 |        5 |     90% |38, 47, 70, 116, 147-149 |
| src/pretalx/api/serializers/speaker\_information.py                        |       35 |        1 |        6 |        1 |     95% |        63 |
| src/pretalx/api/serializers/submission.py                                  |      212 |       21 |       68 |       15 |     86% |82, 94, 120, 171, 185, 330-336, 342->344, 345, 350, 352-354, 363-364, 376, 378-379, 381, 383, 385 |
| src/pretalx/api/serializers/team.py                                        |       49 |        0 |        8 |        0 |    100% |           |
| src/pretalx/api/shims.py                                                   |       18 |       18 |        0 |        0 |      0% |     11-35 |
| src/pretalx/api/versions.py                                                |       30 |        1 |       10 |        1 |     95% |        35 |
| src/pretalx/api/views/access\_code.py                                      |       27 |        2 |        2 |        0 |     93% |     59-60 |
| src/pretalx/api/views/event.py                                             |       24 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/feedback.py                                          |       37 |        1 |       10 |        1 |     96% |        75 |
| src/pretalx/api/views/mail.py                                              |       15 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/mixins.py                                            |       77 |        3 |       16 |        6 |     90% |45->47, 62->65, 68->71, 72->76, 106, 116-119 |
| src/pretalx/api/views/question.py                                          |      115 |        9 |       18 |        3 |     89% |108-112, 159, 172-173, 258-259, 289->301 |
| src/pretalx/api/views/review.py                                            |       42 |        1 |       10 |        1 |     96% |       112 |
| src/pretalx/api/views/room.py                                              |       32 |        2 |        2 |        0 |     94% |     65-66 |
| src/pretalx/api/views/root.py                                              |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/schedule.py                                          |      129 |        8 |       36 |        8 |     90% |80, 90, 114, 148, 222, 300, 316, 322 |
| src/pretalx/api/views/speaker.py                                           |       55 |        1 |       12 |        1 |     97% |       157 |
| src/pretalx/api/views/speaker\_information.py                              |       19 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/submission.py                                        |      231 |       28 |       28 |        5 |     86% |240, 261, 269, 276, 290-293, 303-306, 316-319, 329-332, 342-345, 397-400 |
| src/pretalx/api/views/team.py                                              |       93 |        4 |        8 |        0 |     96% |83-84, 187-188 |
| src/pretalx/api/views/upload.py                                            |       37 |        5 |        8 |        2 |     84% | 64, 75-78 |
| src/pretalx/cfp/apps.py                                                    |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/flow.py                                                    |      532 |        9 |      150 |        7 |     97% |177, 448-450, 700-701, 715, 721->724, 782, 786, 802->804, 804->814 |
| src/pretalx/cfp/forms/auth.py                                              |       26 |        0 |        2 |        0 |    100% |           |
| src/pretalx/cfp/forms/cfp.py                                               |       31 |        3 |       20 |        2 |     90% | 45-47, 53 |
| src/pretalx/cfp/forms/submissions.py                                       |       43 |        4 |       10 |        1 |     87% |     53-56 |
| src/pretalx/cfp/phrases.py                                                 |       21 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/signals.py                                                 |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/auth.py                                              |       91 |       25 |       10 |        1 |     66% |47, 51, 108, 112-138 |
| src/pretalx/cfp/views/event.py                                             |       57 |        6 |       10 |        3 |     84% |30, 62, 82, 92-95 |
| src/pretalx/cfp/views/locale.py                                            |       20 |        1 |        6 |        2 |     88% |21->40, 32 |
| src/pretalx/cfp/views/robots.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/user.py                                              |      362 |       13 |       66 |       11 |     94% |143, 166, 258, 370, 375, 378->372, 418-419, 460->464, 468, 480, 482, 501->503, 613-614, 633 |
| src/pretalx/cfp/views/wizard.py                                            |       82 |        0 |       36 |        0 |    100% |           |
| src/pretalx/common/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/auth.py                                                 |       20 |        3 |        4 |        1 |     83% | 31-32, 35 |
| src/pretalx/common/cache.py                                                |       48 |        0 |       10 |        0 |    100% |           |
| src/pretalx/common/checks.py                                               |       63 |       47 |       28 |        0 |     18% |14-52, 57-67, 72-83, 88-112, 117-128, 133-156 |
| src/pretalx/common/context\_processors.py                                  |       57 |        0 |       14 |        0 |    100% |           |
| src/pretalx/common/db.py                                                   |       10 |        3 |        0 |        0 |     70% |     19-21 |
| src/pretalx/common/diff\_utils.py                                          |       49 |        2 |       22 |        3 |     93% |62, 64, 88->81 |
| src/pretalx/common/exceptions.py                                           |       60 |       38 |       22 |        0 |     27% |56-61, 64-70, 73-81, 86-88, 91, 94-103, 110-113 |
| src/pretalx/common/exporter.py                                             |       68 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/formats/en/formats.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/fields.py                                         |      181 |        8 |       60 |        9 |     93% |66, 92, 114, 166, 222->exit, 246-247, 308->306, 319, 335 |
| src/pretalx/common/forms/forms.py                                          |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/mixins.py                                         |      309 |       32 |      150 |       30 |     86% |66->60, 113, 162, 164, 255->260, 257, 259, 270-279, 304->309, 401->403, 403->405, 415->417, 417->419, 422->424, 424->426, 440->442, 442->444, 445, 487, 489->508, 495, 500, 519->521, 526-527, 539->541, 567-577, 580, 583-589, 591, 592->562, 596-598 |
| src/pretalx/common/forms/renderers.py                                      |       18 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/forms/tables.py                                         |       40 |        1 |       16 |        2 |     95% |61, 97->102 |
| src/pretalx/common/forms/validators.py                                     |       51 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/forms/widgets.py                                        |      229 |        4 |       28 |        4 |     97% |196, 352, 426, 437 |
| src/pretalx/common/image.py                                                |      105 |       62 |       40 |        6 |     35% |40-82, 87-90, 101-108, 118-140, 159, 162, 166, 173-180, 186, 191 |
| src/pretalx/common/language.py                                             |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/log\_display.py                                         |       86 |       10 |       38 |        6 |     87% |164, 181, 190-195, 197-199, 236, 239 |
| src/pretalx/common/mail.py                                                 |       54 |        4 |       18 |        2 |     89% |83, 134-136 |
| src/pretalx/common/management/commands/create\_test\_event.py              |      185 |        5 |       60 |        2 |     96% |150->exit, 155, 163-166 |
| src/pretalx/common/management/commands/devserver.py                        |       16 |       16 |        4 |        0 |      0% |     10-40 |
| src/pretalx/common/management/commands/init.py                             |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/makemessages.py                     |       50 |        6 |       20 |        4 |     83% |45->47, 48-49, 57, 71-73 |
| src/pretalx/common/management/commands/makemigrations.py                   |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/management/commands/migrate.py                          |       13 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/management/commands/move\_event.py                      |       29 |        0 |        4 |        1 |     97% |  39->exit |
| src/pretalx/common/management/commands/rebuild.py                          |       35 |        3 |        2 |        1 |     89% | 49-50, 68 |
| src/pretalx/common/management/commands/runperiodic.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/shell.py                            |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/spectacular.py                      |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/update\_translation\_percentages.py |       39 |       39 |       10 |        0 |      0% |      4-61 |
| src/pretalx/common/middleware/domains.py                                   |      123 |       14 |       44 |        7 |     84% |45, 79->84, 85, 98-116, 166->172, 172->188, 208-209, 233-238 |
| src/pretalx/common/middleware/event.py                                     |      112 |       12 |       42 |        4 |     86% |94-96, 118-122, 163-171, 185->exit, 197->exit |
| src/pretalx/common/models/choices.py                                       |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/models/fields.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/models/file.py                                          |       23 |        2 |        2 |        0 |     84% |     41-43 |
| src/pretalx/common/models/log.py                                           |       80 |        9 |       32 |        9 |     82% |64-67, 89, 92->96, 101, 104, 109, 113->128, 118->128, 121 |
| src/pretalx/common/models/mixins.py                                        |      179 |       23 |       72 |        3 |     86% |47, 129, 291->exit, 296-297, 316-319, 322, 325, 328, 331, 335, 338-348 |
| src/pretalx/common/models/transaction.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/plugins.py                                              |       30 |        0 |        8 |        1 |     97% |    63->69 |
| src/pretalx/common/settings/config.py                                      |       23 |        1 |        2 |        1 |     92% |       172 |
| src/pretalx/common/signals.py                                              |      117 |       14 |       34 |        3 |     89% |37, 79, 174, 180-185, 189-190, 195-197 |
| src/pretalx/common/tables.py                                               |      414 |       54 |      174 |       30 |     84% |28->exit, 63, 65->68, 85-87, 90-91, 144->142, 149->151, 173, 217-218, 262, 269, 295, 298-300, 303->306, 310-316, 330, 395->397, 400-401, 404->408, 446-448, 481, 486, 499, 505, 509-512, 579, 590-592, 646, 657->659, 662-663, 681->683, 696, 711-713, 719, 724, 734-736, 739-740 |
| src/pretalx/common/tasks.py                                                |       40 |       14 |       14 |        3 |     57% |27, 38-39, 54-68 |
| src/pretalx/common/templatetags/copyable.py                                |       11 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/templatetags/datetimerange.py                           |       28 |        5 |        6 |        3 |     76% |31, 33, 46-48 |
| src/pretalx/common/templatetags/event\_tags.py                             |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/filesize.py                                |       13 |        3 |        4 |        1 |     76% | 13-14, 19 |
| src/pretalx/common/templatetags/form\_media.py                             |       44 |        6 |       28 |        2 |     81% | 40, 59-68 |
| src/pretalx/common/templatetags/history\_sidebar.py                        |       77 |       41 |       26 |        8 |     43% |16-24, 32->36, 49-51, 55-60, 72, 74, 84-85, 87-88, 90-91, 93-95, 97-120 |
| src/pretalx/common/templatetags/html\_signal.py                            |       12 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/templatetags/phrases.py                                 |       11 |        1 |        2 |        1 |     85% |        20 |
| src/pretalx/common/templatetags/rich\_text.py                              |       54 |        1 |        6 |        0 |     98% |       196 |
| src/pretalx/common/templatetags/safelink.py                                |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/thumbnail.py                               |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/templatetags/times.py                                   |       13 |        0 |        6 |        0 |    100% |           |
| src/pretalx/common/templatetags/vite.py                                    |       56 |       28 |       24 |        5 |     41% |20-24, 32, 40-58, 69, 74-84, 91 |
| src/pretalx/common/templatetags/xmlescape.py                               |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/text/console.py                                         |       65 |       24 |       18 |        3 |     65% |42-43, 49-50, 64-65, 82, 88-126 |
| src/pretalx/common/text/css.py                                             |       31 |        0 |       14 |        0 |    100% |           |
| src/pretalx/common/text/daterange.py                                       |       33 |        0 |       18 |        0 |    100% |           |
| src/pretalx/common/text/path.py                                            |       19 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/text/phrases.py                                         |       52 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/text/serialize.py                                       |       27 |        1 |        8 |        1 |     94% |        40 |
| src/pretalx/common/ui.py                                                   |       52 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/update\_check.py                                        |       67 |        0 |       20 |        0 |    100% |           |
| src/pretalx/common/views/cache.py                                          |       63 |       11 |       32 |       14 |     74% |20, 26, 53, 76, 78, 80, 86->89, 106->109, 115, 117, 120, 126, 132->138, 139 |
| src/pretalx/common/views/errors.py                                         |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/views/generic.py                                        |      497 |       66 |      144 |       21 |     82% |72-77, 88-98, 139->142, 190-191, 213, 218-219, 300-301, 320, 328-330, 367->exit, 377-379, 416, 419, 422-435, 453->455, 458-460, 464, 503->506, 513->522, 519->522, 594->exit, 621->629, 630-651, 662, 677-678, 685-686, 704->706, 712->714, 724 |
| src/pretalx/common/views/helpers.py                                        |        8 |        1 |        0 |        0 |     88% |        31 |
| src/pretalx/common/views/mixins.py                                         |      244 |       72 |       90 |       15 |     66% |35, 39, 41-42, 52-76, 86-87, 103-110, 127, 163-164, 176-180, 185, 195-196, 217, 243, 261-263, 265, 267, 283-293, 301, 335-339, 365-373 |
| src/pretalx/common/views/redirect.py                                       |       26 |       11 |        6 |        0 |     47% |13-23, 33-43 |
| src/pretalx/common/views/shortlink.py                                      |       27 |        0 |       16 |        0 |    100% |           |
| src/pretalx/event/apps.py                                                  |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/event/forms.py                                                 |      162 |        7 |       34 |        5 |     94% |72-75, 128-129, 142, 237->exit, 292-293, 362->exit |
| src/pretalx/event/models/event.py                                          |      562 |       31 |      124 |       10 |     93% |85, 463, 468, 514, 517, 666-668, 697->711, 729, 733-744, 766-767, 775, 817-826, 964->967 |
| src/pretalx/event/models/organiser.py                                      |      119 |        8 |       18 |        6 |     90% |48, 55, 69, 77, 258, 266, 273, 315 |
| src/pretalx/event/rules.py                                                 |       52 |        0 |       12 |        0 |    100% |           |
| src/pretalx/event/services.py                                              |       36 |        1 |       12 |        1 |     96% |        80 |
| src/pretalx/event/stages.py                                                |       39 |        0 |       10 |        0 |    100% |           |
| src/pretalx/event/utils.py                                                 |        7 |        0 |        2 |        0 |    100% |           |
| src/pretalx/mail/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/context.py                                                |       70 |        4 |       36 |        4 |     92% |31, 42, 61, 74 |
| src/pretalx/mail/default\_templates.py                                     |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/models.py                                                 |      194 |        8 |       56 |        6 |     94% |34, 242-258, 260, 267, 390, 447 |
| src/pretalx/mail/placeholders.py                                           |       40 |        3 |        2 |        0 |     93% |16, 28, 50 |
| src/pretalx/mail/signals.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/context\_processors.py                                    |       42 |        0 |       18 |        1 |     98% |    17->14 |
| src/pretalx/orga/forms/cfp.py                                              |      299 |       50 |       80 |       20 |     77% |89->exit, 162, 164, 174-188, 207, 214, 222-255, 321->323, 324, 332, 348->exit, 357->359, 360, 385, 509, 510->exit, 523, 525, 547, 628->631 |
| src/pretalx/orga/forms/event.py                                            |      383 |       52 |      114 |       25 |     82% |193, 219-220, 260, 272, 281->289, 291-294, 309, 315->exit, 449, 462-464, 467, 476, 653-661, 693, 711, 734-737, 751-758, 760-763, 793->795, 803-807, 924->exit, 937-939, 961-962, 964, 969-974, 977, 985, 989 |
| src/pretalx/orga/forms/export.py                                           |       93 |        2 |       34 |        2 |     97% |  125, 145 |
| src/pretalx/orga/forms/mails.py                                            |      275 |       35 |       90 |       18 |     83% |35->37, 64, 71-72, 80-81, 88-89, 118, 136-137, 140-157, 168, 186->204, 198-199, 230, 265, 327-335, 342, 354-355, 411-412, 443->445, 468->467, 494, 497->500, 511 |
| src/pretalx/orga/forms/review.py                                           |      277 |       34 |       80 |       17 |     83% |36, 79, 126, 134-135, 148, 156, 163, 165, 221-222, 251, 281-283, 299-305, 365, 395, 412, 434, 491, 496-497, 500->504, 506-507, 513-514, 522 |
| src/pretalx/orga/forms/schedule.py                                         |      119 |       30 |       14 |        2 |     71% |42->exit, 204, 219, 222-224, 227-229, 232-234, 237-238, 241-242, 245-246, 249-250, 253-254, 257-258, 261, 264, 267, 270, 273, 276, 279 |
| src/pretalx/orga/forms/speaker.py                                          |       46 |        4 |        2 |        1 |     90% |74, 82, 85, 93 |
| src/pretalx/orga/forms/submission.py                                       |      178 |       17 |       78 |       15 |     87% |68-70, 111->113, 116, 119->127, 139, 143, 154, 163, 170, 179, 188->190, 197, 221-223, 279, 366-367 |
| src/pretalx/orga/forms/widgets.py                                          |       47 |        2 |        0 |        0 |     96% |     96-97 |
| src/pretalx/orga/permissions.py                                            |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/phrases.py                                                |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/receivers.py                                              |       16 |        2 |        4 |        2 |     80% |    17, 29 |
| src/pretalx/orga/rules.py                                                  |        8 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/signals.py                                                |       28 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/cfp.py                                             |       84 |        4 |        6 |        3 |     92% |70, 92, 258, 260 |
| src/pretalx/orga/tables/mail.py                                            |       36 |        3 |        2 |        0 |     87% |   110-112 |
| src/pretalx/orga/tables/organiser.py                                       |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/schedule.py                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/speaker.py                                         |       58 |        4 |        4 |        2 |     90% |42, 45, 51, 150 |
| src/pretalx/orga/tables/submission.py                                      |      169 |       39 |       60 |        6 |     68% |121->123, 132, 160, 163, 236, 238-239, 245->247, 274-276, 317, 328-332, 335-372 |
| src/pretalx/orga/templatetags/formsets.py                                  |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/orga\_edit\_link.py                          |       10 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/templatetags/platform\_icons.py                           |        9 |        1 |        2 |        1 |     82% |        16 |
| src/pretalx/orga/templatetags/querystring.py                               |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/review\_score.py                             |       17 |        1 |        8 |        1 |     92% |        25 |
| src/pretalx/orga/utils/i18n.py                                             |       39 |        5 |       12 |        2 |     82% |183-184, 210-212 |
| src/pretalx/orga/views/auth.py                                             |       59 |        2 |        8 |        2 |     94% |    41, 53 |
| src/pretalx/orga/views/cards.py                                            |       17 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/views/cfp.py                                              |      712 |       61 |      212 |       43 |     88% |96, 99, 110-111, 115->119, 159, 167, 191, 195, 198->192, 220, 227, 229, 231, 233-235, 265-271, 289, 299->302, 303, 307-318, 374->368, 376->368, 457, 528, 580-581, 664, 665->667, 669->671, 671->674, 735, 748, 796, 798, 857->859, 871->870, 903-908, 927-928, 975->974, 987-988, 1017-1018, 1021, 1025, 1043, 1062, 1113, 1126, 1165-1171 |
| src/pretalx/orga/views/dashboard.py                                        |      161 |       28 |       46 |        9 |     78% |31-43, 80, 109-115, 137-138, 157-168, 220, 237-240, 286-287, 296->308, 353-354, 363-370 |
| src/pretalx/orga/views/event.py                                            |      428 |       28 |      114 |       25 |     89% |154-155, 203, 270, 316, 356, 358->363, 387, 392->390, 407, 415, 419, 425, 455, 459->457, 461, 471-472, 475-479, 482, 582-588, 656, 676, 699-700, 724->723, 727->729, 730, 773->778 |
| src/pretalx/orga/views/mails.py                                            |      349 |       54 |       70 |       14 |     80% |52-53, 182-184, 194, 203-205, 255-261, 333-335, 369->377, 373, 399, 404-405, 432, 456, 462-507, 534-536, 551, 557, 570-572, 576, 579, 582-587 |
| src/pretalx/orga/views/organiser.py                                        |      309 |       40 |       56 |        8 |     81% |118-120, 141-142, 157-158, 166-168, 292-293, 334, 381, 394, 396-412, 426, 429, 434, 439-458, 461, 464-468, 471-473 |
| src/pretalx/orga/views/person.py                                           |      120 |       20 |       30 |        5 |     81% |77-86, 90-97, 99-107, 156, 165, 181-182 |
| src/pretalx/orga/views/plugins.py                                          |       36 |        0 |        6 |        0 |    100% |           |
| src/pretalx/orga/views/review.py                                           |      503 |       63 |      106 |       18 |     84% |85, 88-91, 93-96, 248->250, 250->256, 291->exit, 312-313, 315-321, 354, 363-368, 373, 379-384, 389, 398-412, 434, 448-455, 496-497, 508-509, 520->533, 537, 717-718, 729-732, 734-738, 895-896, 899-900, 954, 984-985 |
| src/pretalx/orga/views/schedule.py                                         |      326 |       28 |       62 |       10 |     88% |53->60, 131-132, 164-165, 188, 377, 378->381, 390, 420, 443, 455, 465, 475-506, 524, 566, 631-638 |
| src/pretalx/orga/views/speaker.py                                          |      201 |       10 |       22 |        5 |     92% |93-105, 107-110, 234, 308, 371-372 |
| src/pretalx/orga/views/submission.py                                       |      634 |       31 |      112 |       20 |     93% |194-198, 222, 239-245, 366, 374, 398, 486, 489->483, 526, 549->560, 561, 569->581, 579->581, 639, 671->673, 692->exit, 694, 761-762, 795->805, 847, 901, 928, 1174, 1178, 1182, 1189-1195, 1217-1218 |
| src/pretalx/orga/views/typeahead.py                                        |       59 |       16 |       16 |        5 |     64% |45, 54, 63, 104-109, 114, 119-131, 154, 193-196 |
| src/pretalx/person/apps.py                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/exporters.py                                            |       23 |        1 |        4 |        1 |     93% |        33 |
| src/pretalx/person/forms/auth.py                                           |       43 |        2 |       10 |        2 |     92% |    41, 48 |
| src/pretalx/person/forms/auth\_token.py                                    |       43 |       17 |       10 |        0 |     53% |61-63, 76-95 |
| src/pretalx/person/forms/information.py                                    |       21 |        1 |        2 |        1 |     91% |        18 |
| src/pretalx/person/forms/profile.py                                        |      188 |       31 |       68 |       14 |     79% |65->67, 89-90, 91->96, 106->exit, 127->129, 140, 155, 157, 159, 173, 204->exit, 211, 227-233, 236-237, 289->exit, 307, 333-338, 341-350 |
| src/pretalx/person/forms/user.py                                           |       87 |        6 |       26 |        4 |     91% |80, 83-84, 113, 125, 170 |
| src/pretalx/person/models/auth\_token.py                                   |       73 |       11 |       20 |        0 |     82% |101, 104, 146-155 |
| src/pretalx/person/models/information.py                                   |       30 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/models/preferences.py                                   |       41 |        5 |       18 |        3 |     83% |47-53, 92, 109->112 |
| src/pretalx/person/models/profile.py                                       |       58 |        2 |        6 |        3 |     92% |119, 140, 146->exit, 151->exit, 156->162 |
| src/pretalx/person/models/user.py                                          |      274 |        7 |       54 |        8 |     95% |88, 246->250, 256->259, 264, 277, 378->380, 383, 451-453, 478->493 |
| src/pretalx/person/rules.py                                                |       33 |        2 |       10 |        2 |     91% |    44, 46 |
| src/pretalx/person/services.py                                             |        9 |        0 |        2 |        1 |     91% |    20->22 |
| src/pretalx/person/signals.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/tasks.py                                                |       47 |       17 |       14 |        1 |     57% |     43-65 |
| src/pretalx/schedule/apps.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/ascii.py                                              |      127 |       30 |       54 |        8 |     71% |66->69, 72->75, 77-81, 92-96, 97->exit, 102-114, 144, 147-168, 182 |
| src/pretalx/schedule/exporters.py                                          |      119 |        4 |       22 |        0 |     96% |   337-343 |
| src/pretalx/schedule/forms.py                                              |       54 |        0 |        8 |        1 |     98% |    65->68 |
| src/pretalx/schedule/ical.py                                               |       37 |        2 |        4 |        0 |     95% |     24-25 |
| src/pretalx/schedule/models/availability.py                                |       88 |        1 |       34 |        1 |     98% |55, 76->79 |
| src/pretalx/schedule/models/room.py                                        |       44 |        3 |        4 |        2 |     90% |94, 101, 104 |
| src/pretalx/schedule/models/schedule.py                                    |      208 |       30 |       70 |        8 |     83% |151-192, 239->241, 283, 287, 357, 369-377, 388-396, 423->425, 523 |
| src/pretalx/schedule/models/slot.py                                        |      123 |        5 |       22 |        2 |     94% |198-205, 216 |
| src/pretalx/schedule/notifications.py                                      |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/schedule/phrases.py                                            |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/services.py                                           |      226 |        6 |       90 |       11 |     94% |71->73, 76->78, 78->80, 80->82, 82->75, 121-123, 127->125, 138->130, 141->143, 143->146, 335, 429-430 |
| src/pretalx/schedule/signals.py                                            |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/tasks.py                                              |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/utils.py                                              |       14 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/apps.py                                             |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/cards.py                                            |       87 |        1 |       10 |        1 |     98% |        34 |
| src/pretalx/submission/exporters.py                                        |       45 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/forms/comment.py                                    |       18 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/forms/feedback.py                                   |       23 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/forms/question.py                                   |       67 |        0 |       30 |        2 |     98% |87->exit, 109->108 |
| src/pretalx/submission/forms/resource.py                                   |       25 |        2 |        6 |        2 |     87% |    31, 35 |
| src/pretalx/submission/forms/submission.py                                 |      252 |       31 |      108 |       16 |     85% |113, 156, 170, 175->exit, 180, 220, 224-225, 228, 235-242, 265->267, 420, 436-442, 484-497, 499-502, 509, 523-526, 531 |
| src/pretalx/submission/forms/tag.py                                        |       21 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/icons.py                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/access\_code.py                              |       56 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/models/cfp.py                                       |       82 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/models/comment.py                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/feedback.py                                  |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/question.py                                  |      225 |        8 |       48 |        5 |     94% |371, 375-376, 391, 433->436, 540, 582->589, 584, 587-588 |
| src/pretalx/submission/models/resource.py                                  |       36 |        0 |        6 |        2 |     95% |59->exit, 66->exit |
| src/pretalx/submission/models/review.py                                    |      132 |       11 |       26 |        7 |     86% |55-56, 59->exit, 72, 76-78, 95, 98->102, 103, 108, 201, 317 |
| src/pretalx/submission/models/submission.py                                |      531 |       40 |      124 |       17 |     90% |404-406, 482, 527->547, 533, 535, 539-541, 554-555, 673->679, 695-696, 798->exit, 805, 821-823, 826, 909, 922-937, 986, 1018, 1068-1070, 1081-1086, 1175->exit, 1194-1206, 1223->exit, 1285 |
| src/pretalx/submission/models/tag.py                                       |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/track.py                                     |       34 |        1 |        0 |        0 |     97% |        89 |
| src/pretalx/submission/models/type.py                                      |       39 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/phrases.py                                          |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/rules.py                                            |      210 |       11 |       56 |        7 |     93% |12-13, 29-30, 217, 224, 255, 267, 296, 373, 388 |
| src/pretalx/submission/signals.py                                          |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/tasks.py                                            |       15 |        3 |        4 |        2 |     74% | 21-22, 26 |
| src/tests/agenda/test\_agenda\_permissions.py                              |       22 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_schedule\_export.py                         |      384 |        3 |       18 |        5 |     98% |38, 60, 610->614, 615->618, 632 |
| src/tests/agenda/test\_agenda\_widget.py                                   |       41 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_featured.py                           |       57 |        0 |        4 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_feedback.py                           |       63 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_schedule.py                           |      240 |        0 |       12 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_talks.py                              |      197 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_widget.py                             |       42 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_access\_code.py                                   |      116 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_answers.py                                        |      134 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_events.py                                         |       45 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_feedback.py                                       |      167 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_mail.py                                           |      108 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_questions.py                                      |      446 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_reviews.py                                        |      370 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_rooms.py                                          |      205 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_root.py                                           |       13 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_schedule.py                                       |      498 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_speaker\_information.py                           |      141 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_speakers.py                                       |      299 |        0 |        4 |        0 |    100% |           |
| src/tests/api/test\_api\_submissions.py                                    |      812 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_teams.py                                          |      208 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_upload.py                                         |       30 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/test\_cfp\_flow.py                                           |      124 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_auth.py                                     |      139 |        0 |        2 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_base.py                                     |       70 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_user.py                                     |      787 |        0 |       12 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_view\_flow.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_wizard.py                                   |      447 |        1 |       22 |        1 |     99% |       208 |
| src/tests/common/forms/test\_cfp\_forms\_utils.py                          |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/forms/test\_cfp\_forms\_validators.py                     |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/forms/test\_common\_form\_widgets.py                      |       50 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_log.py                                         |       43 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_middleware.py                                  |       57 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_serialize.py                                   |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_cache.py                                    |       39 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_console.py                                  |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_css.py                                      |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_exporter.py                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_forms\_utils.py                             |        9 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_mail.py                                     |       27 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_management\_commands.py                     |       61 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_middleware\_domains.py                      |       12 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_models\_log.py                              |       76 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_plugins.py                                  |       24 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_signals.py                                  |       32 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_templatetags.py                             |       35 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_ui.py                                       |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_utils.py                                    |       25 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_diff\_utils.py                                      |       59 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_update\_check.py                                    |      117 |        0 |        0 |        0 |    100% |           |
| src/tests/common/views/test\_shortlink.py                                  |       84 |        0 |        0 |        0 |    100% |           |
| src/tests/conftest.py                                                      |      547 |        0 |       12 |        0 |    100% |           |
| src/tests/dummy\_app.py                                                    |       13 |        0 |        0 |        0 |    100% |           |
| src/tests/dummy\_signals.py                                                |       46 |        0 |        6 |        0 |    100% |           |
| src/tests/event/test\_event\_model.py                                      |      170 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_services.py                                   |       87 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_stages.py                                     |       24 |        0 |        6 |        0 |    100% |           |
| src/tests/event/test\_event\_utils.py                                      |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/mail/test\_mail\_models.py                                       |       47 |        0 |        4 |        0 |    100% |           |
| src/tests/orga/test\_orga\_access.py                                       |       71 |        0 |       12 |        0 |    100% |           |
| src/tests/orga/test\_orga\_auth.py                                         |      145 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_forms.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_permissions.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_orga\_utils.py                                        |        6 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/test\_templatetags.py                                       |       18 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_tables.py                                 |      282 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_admin.py                           |       86 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_cfp.py                             |      712 |        0 |        2 |        1 |     99% | 165->exit |
| src/tests/orga/views/test\_orga\_views\_dashboard.py                       |      112 |        0 |       40 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_event.py                           |      461 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_mail.py                            |      385 |        0 |       10 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_organiser.py                       |      329 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_person.py                          |       44 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_review.py                          |      348 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_schedule.py                        |      308 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_speaker.py                         |      216 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission.py                      |      611 |        0 |        6 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission\_cards.py               |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_auth\_token\_model.py                               |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_information\_model.py                               |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_person\_permissions.py                              |       10 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_person\_tasks.py                                    |       34 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_user\_model.py                                      |       70 |        0 |        0 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_availability.py                         |       59 |        0 |        4 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_exporters.py                            |       28 |        0 |        0 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_forms.py                                |      105 |        0 |       10 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_model.py                                |      199 |        0 |        2 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_models\_slot.py                         |       75 |        0 |        6 |        0 |    100% |           |
| src/tests/schedule/test\_schedule\_utils.py                                |       25 |        0 |        2 |        0 |    100% |           |
| src/tests/services/test\_documentation.py                                  |       37 |        0 |       12 |        0 |    100% |           |
| src/tests/services/test\_models.py                                         |        8 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_access\_code\_model.py                          |        7 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_cfp\_model.py                                   |       15 |        0 |        2 |        0 |    100% |           |
| src/tests/submission/test\_question\_model.py                              |       59 |        0 |        4 |        0 |    100% |           |
| src/tests/submission/test\_review\_model.py                                |       19 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_model.py                            |      295 |        0 |        6 |        0 |    100% |           |
| src/tests/submission/test\_submission\_permissions.py                      |       41 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_type\_model.py                      |       21 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                                                                  | **33732** | **1934** | **5404** |  **761** | **92%** |           |


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