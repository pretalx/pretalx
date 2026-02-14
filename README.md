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
| src/pretalx/agenda/tasks.py                                                |       34 |        0 |        8 |        2 |     95% |44->exit, 46->exit |
| src/pretalx/agenda/views/featured.py                                       |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/feed.py                                           |       34 |        0 |        2 |        0 |    100% |           |
| src/pretalx/agenda/views/schedule.py                                       |      137 |        2 |       36 |        1 |     98% |   64, 145 |
| src/pretalx/agenda/views/speaker.py                                        |       99 |        9 |       18 |        3 |     86% |78, 108-114, 152, 162-163 |
| src/pretalx/agenda/views/talk.py                                           |      166 |        5 |       26 |        4 |     93% |72->71, 78->71, 161-164, 175-176 |
| src/pretalx/agenda/views/utils.py                                          |       51 |        6 |       22 |        4 |     86% |21, 59, 61, 65-69, 77->79 |
| src/pretalx/agenda/views/widget.py                                         |       85 |        6 |       30 |        3 |     92% |47, 92-95, 110 |
| src/pretalx/api/apps.py                                                    |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/documentation.py                                           |       26 |        0 |        4 |        1 |     97% |    11->26 |
| src/pretalx/api/exceptions.py                                              |        9 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/filters/answer.py                                          |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/feedback.py                                        |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/filters/review.py                                          |       27 |        0 |        2 |        1 |     97% |  65->exit |
| src/pretalx/api/filters/schedule.py                                        |       23 |        0 |        4 |        1 |     96% |  41->exit |
| src/pretalx/api/filters/submission.py                                      |       10 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/pagination.py                                              |       23 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/permissions.py                                             |       32 |        0 |       14 |        0 |    100% |           |
| src/pretalx/api/serializers/access\_code.py                                |       19 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/availability.py                                |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/event.py                                       |       23 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/feedback.py                                    |       35 |        1 |        6 |        1 |     95% |        43 |
| src/pretalx/api/serializers/fields.py                                      |       25 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/serializers/log.py                                         |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/serializers/mail.py                                        |       29 |        2 |        4 |        0 |     94% |     36-37 |
| src/pretalx/api/serializers/mixins.py                                      |       38 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/question.py                                    |      126 |        6 |       32 |        1 |     92% |   279-288 |
| src/pretalx/api/serializers/review.py                                      |       74 |        0 |       12 |        0 |    100% |           |
| src/pretalx/api/serializers/room.py                                        |       30 |        0 |        4 |        0 |    100% |           |
| src/pretalx/api/serializers/schedule.py                                    |       71 |        1 |       12 |        1 |     98% |        38 |
| src/pretalx/api/serializers/speaker.py                                     |       90 |        7 |       26 |        5 |     90% |38, 47, 70, 116, 147-149 |
| src/pretalx/api/serializers/speaker\_information.py                        |       35 |        1 |        6 |        1 |     95% |        63 |
| src/pretalx/api/serializers/submission.py                                  |      235 |       21 |       72 |       15 |     88% |121, 133, 159, 210, 224, 374-380, 386->388, 389, 394, 396-398, 407-408, 420, 422-423, 425, 427, 429 |
| src/pretalx/api/serializers/team.py                                        |       49 |        0 |        8 |        0 |    100% |           |
| src/pretalx/api/shims.py                                                   |       18 |       18 |        0 |        0 |      0% |     11-35 |
| src/pretalx/api/versions.py                                                |       30 |        1 |       10 |        1 |     95% |        35 |
| src/pretalx/api/views/access\_code.py                                      |       27 |        2 |        2 |        0 |     93% |     59-60 |
| src/pretalx/api/views/event.py                                             |       24 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/feedback.py                                          |       37 |        1 |       10 |        1 |     96% |        75 |
| src/pretalx/api/views/mail.py                                              |       15 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/mixins.py                                            |       77 |        3 |       16 |        6 |     90% |45->47, 62->65, 68->71, 72->76, 106, 116-119 |
| src/pretalx/api/views/question.py                                          |      107 |        9 |       18 |        3 |     89% |108-112, 159, 172-173, 241-242, 272->284 |
| src/pretalx/api/views/review.py                                            |       45 |        1 |       12 |        1 |     96% |       117 |
| src/pretalx/api/views/room.py                                              |       32 |        2 |        2 |        0 |     94% |     65-66 |
| src/pretalx/api/views/root.py                                              |       19 |        0 |        0 |        0 |    100% |           |
| src/pretalx/api/views/schedule.py                                          |      129 |        8 |       36 |        8 |     90% |80, 90, 114, 148, 222, 300, 316, 322 |
| src/pretalx/api/views/speaker.py                                           |       55 |        1 |       12 |        1 |     97% |       157 |
| src/pretalx/api/views/speaker\_information.py                              |       19 |        0 |        2 |        0 |    100% |           |
| src/pretalx/api/views/submission.py                                        |      241 |       18 |       28 |        5 |     91% |247, 268, 272, 287, 300-301, 309-310, 318-319, 327-328, 336-337, 388-391 |
| src/pretalx/api/views/team.py                                              |       93 |        4 |        8 |        0 |     96% |83-84, 187-188 |
| src/pretalx/api/views/upload.py                                            |       37 |        5 |        8 |        2 |     84% | 64, 75-78 |
| src/pretalx/cfp/apps.py                                                    |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/flow.py                                                    |      532 |        9 |      150 |        7 |     97% |177, 448-450, 700-701, 715, 721->724, 782, 786, 802->804, 804->814 |
| src/pretalx/cfp/forms/auth.py                                              |       26 |        0 |        2 |        0 |    100% |           |
| src/pretalx/cfp/forms/cfp.py                                               |       31 |        3 |       20 |        2 |     90% | 45-47, 53 |
| src/pretalx/cfp/forms/submissions.py                                       |       43 |        4 |       10 |        1 |     87% |     53-56 |
| src/pretalx/cfp/phrases.py                                                 |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/signals.py                                                 |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/auth.py                                              |       91 |       25 |       10 |        1 |     66% |47, 51, 108, 112-138 |
| src/pretalx/cfp/views/event.py                                             |       57 |        6 |       10 |        3 |     84% |30, 62, 82, 92-95 |
| src/pretalx/cfp/views/locale.py                                            |       20 |        1 |        6 |        2 |     88% |21->40, 32 |
| src/pretalx/cfp/views/robots.py                                            |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/cfp/views/user.py                                              |      370 |       19 |       66 |       11 |     93% |143, 165, 231-233, 257, 300-302, 375, 380, 383->377, 423-424, 465->469, 473, 485, 487, 504->506, 616-617, 645 |
| src/pretalx/cfp/views/wizard.py                                            |       82 |        0 |       36 |        0 |    100% |           |
| src/pretalx/common/apps.py                                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/auth.py                                                 |       20 |        3 |        4 |        1 |     83% | 31-32, 35 |
| src/pretalx/common/cache.py                                                |       48 |        0 |       10 |        0 |    100% |           |
| src/pretalx/common/checks.py                                               |       66 |       40 |       30 |        3 |     32% |16-54, 59-69, 74-85, 91, 96-97, 106, 128-139, 144-167 |
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
| src/pretalx/common/forms/widgets.py                                        |      230 |        4 |       28 |        4 |     97% |199, 355, 429, 440 |
| src/pretalx/common/image.py                                                |      105 |       62 |       40 |        6 |     35% |40-82, 87-90, 101-108, 118-140, 159, 162, 166, 173-180, 186, 191 |
| src/pretalx/common/language.py                                             |       22 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/log\_display.py                                         |       86 |       10 |       38 |        6 |     87% |171, 188, 197-202, 204-206, 243, 246 |
| src/pretalx/common/mail.py                                                 |       59 |        4 |       18 |        2 |     90% |89, 142-144 |
| src/pretalx/common/management/commands/create\_test\_event.py              |      185 |        5 |       60 |        2 |     96% |150->exit, 155, 163-166 |
| src/pretalx/common/management/commands/devserver.py                        |       16 |       16 |        4 |        0 |      0% |     10-40 |
| src/pretalx/common/management/commands/init.py                             |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/management/commands/makemessages.py                     |       50 |        6 |       20 |        4 |     83% |45->47, 48-49, 57, 71-73 |
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
| src/pretalx/common/middleware/event.py                                     |      112 |       12 |       42 |        4 |     86% |94-96, 118-122, 163-171, 185->exit, 197->exit |
| src/pretalx/common/models/fields.py                                        |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/models/file.py                                          |       23 |        1 |        2 |        1 |     92% |        43 |
| src/pretalx/common/models/log.py                                           |       73 |        5 |       28 |        8 |     87% |83, 89->93, 98, 101, 106, 110->125, 115->125, 118 |
| src/pretalx/common/models/mixins.py                                        |      210 |       27 |       88 |        6 |     85% |47, 129, 308, 325->323, 349, 352->exit, 356-359, 378-381, 384, 387, 390, 393, 397, 400-410 |
| src/pretalx/common/models/transaction.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/plugins.py                                              |       30 |        0 |        8 |        1 |     97% |    63->69 |
| src/pretalx/common/settings/config.py                                      |       23 |        1 |        2 |        1 |     92% |       172 |
| src/pretalx/common/signals.py                                              |      117 |       14 |       34 |        3 |     89% |37, 79, 174, 180-185, 189-190, 195-197 |
| src/pretalx/common/tables.py                                               |      414 |       54 |      174 |       30 |     84% |28->exit, 63, 65->68, 85-87, 90-91, 144->142, 149->151, 173, 217-218, 262, 269, 295, 298-300, 303->306, 310-316, 330, 395->397, 400-401, 404->408, 446-448, 481, 486, 499, 505, 509-512, 579, 590-592, 646, 657->659, 662-663, 681->683, 696, 711-713, 719, 724, 734-736, 739-740 |
| src/pretalx/common/tasks.py                                                |       40 |        6 |       14 |        6 |     78% |27, 38-39, 55, 60, 66, 69->exit |
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
| src/pretalx/common/templatetags/xmlescape.py                               |        7 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/text/console.py                                         |       65 |       24 |       18 |        3 |     65% |42-43, 49-50, 64-65, 82, 88-124 |
| src/pretalx/common/text/css.py                                             |       31 |        0 |       14 |        0 |    100% |           |
| src/pretalx/common/text/daterange.py                                       |       33 |        0 |       18 |        0 |    100% |           |
| src/pretalx/common/text/path.py                                            |       21 |        4 |        6 |        2 |     70% |32->40, 35-38 |
| src/pretalx/common/text/phrases.py                                         |       52 |        0 |        2 |        0 |    100% |           |
| src/pretalx/common/text/serialize.py                                       |       27 |        1 |        8 |        1 |     94% |        40 |
| src/pretalx/common/text/xml.py                                             |       12 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/ui.py                                                   |       52 |        0 |        0 |        0 |    100% |           |
| src/pretalx/common/update\_check.py                                        |       67 |        0 |       20 |        0 |    100% |           |
| src/pretalx/common/views/cache.py                                          |       63 |       11 |       32 |       14 |     74% |20, 26, 53, 76, 78, 80, 86->89, 106->109, 115, 117, 120, 126, 132->138, 139 |
| src/pretalx/common/views/errors.py                                         |       24 |        0 |        4 |        0 |    100% |           |
| src/pretalx/common/views/generic.py                                        |      503 |       59 |      148 |       23 |     85% |73, 75, 76->69, 89-90, 94-98, 148->151, 199-200, 222, 227-228, 309-310, 329, 337-339, 376->exit, 386-388, 425, 428, 431-444, 462->464, 467-469, 473, 512->515, 522->531, 528->531, 603->exit, 630->638, 639-660, 671, 686-687, 694-695, 713->715, 721->723, 733 |
| src/pretalx/common/views/helpers.py                                        |        8 |        1 |        0 |        0 |     88% |        31 |
| src/pretalx/common/views/mixins.py                                         |      323 |       79 |      114 |       16 |     72% |41, 45, 47-48, 58-82, 92-93, 109-116, 133, 169-170, 182-186, 191, 201-202, 223, 249, 267, 291-301, 309, 343-347, 374, 389-392, 428, 433-440, 471-472, 496, 509-511 |
| src/pretalx/common/views/redirect.py                                       |       26 |       11 |        6 |        0 |     47% |13-23, 33-43 |
| src/pretalx/common/views/shortlink.py                                      |       27 |        0 |       16 |        0 |    100% |           |
| src/pretalx/event/apps.py                                                  |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/event/forms.py                                                 |      162 |        7 |       34 |        5 |     94% |72-75, 128-129, 142, 237->exit, 292-293, 362->exit |
| src/pretalx/event/models/event.py                                          |      566 |       31 |      122 |       11 |     93% |484, 489, 535, 538, 687-689, 718->732, 750, 754-765, 787-788, 796, 838-847, 980, 992->995 |
| src/pretalx/event/models/organiser.py                                      |      118 |        8 |       18 |        6 |     90% |47, 54, 68, 76, 255, 263, 270, 312 |
| src/pretalx/event/rules.py                                                 |       52 |        0 |       12 |        0 |    100% |           |
| src/pretalx/event/services.py                                              |       34 |        3 |       10 |        1 |     91% |     62-66 |
| src/pretalx/event/stages.py                                                |       39 |        0 |       10 |        0 |    100% |           |
| src/pretalx/event/utils.py                                                 |        7 |        0 |        2 |        0 |    100% |           |
| src/pretalx/mail/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/context.py                                                |       70 |        4 |       36 |        4 |     92% |31, 42, 61, 74 |
| src/pretalx/mail/default\_templates.py                                     |       21 |        0 |        0 |        0 |    100% |           |
| src/pretalx/mail/models.py                                                 |      195 |        8 |       56 |        6 |     94% |34, 244-260, 262, 269, 392, 449 |
| src/pretalx/mail/placeholders.py                                           |       40 |        3 |        2 |        0 |     93% |16, 28, 50 |
| src/pretalx/mail/signals.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/apps.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/context\_processors.py                                    |       42 |        0 |       18 |        1 |     98% |    17->14 |
| src/pretalx/orga/forms/cfp.py                                              |      310 |       55 |       84 |       20 |     76% |89->exit, 164, 166, 176-190, 209, 216, 229-275, 342->344, 345, 353, 369->exit, 378->380, 381, 406, 521, 522->exit, 535, 537, 559, 640->643 |
| src/pretalx/orga/forms/event.py                                            |      383 |       52 |      114 |       25 |     82% |193, 219-220, 260, 272, 281->289, 291-294, 309, 315->exit, 451, 464-466, 469, 478, 655-663, 695, 713, 736-739, 753-760, 762-765, 795->797, 805-809, 926->exit, 939-941, 963-964, 966, 971-976, 979, 987, 991 |
| src/pretalx/orga/forms/export.py                                           |       93 |        2 |       34 |        2 |     97% |  125, 145 |
| src/pretalx/orga/forms/mails.py                                            |      258 |       25 |       86 |       18 |     86% |34->36, 63, 70-71, 79-80, 87-88, 117, 137, 155->173, 167-168, 199, 234, 296-304, 311, 323-324, 380-381, 412->414, 437->436, 463, 466->469, 480 |
| src/pretalx/orga/forms/review.py                                           |      277 |       34 |       80 |       17 |     83% |36, 79, 126, 134-135, 148, 156, 163, 165, 237-238, 270, 300-302, 318-324, 384, 414, 431, 453, 510, 515-516, 519->523, 525-526, 532-533, 541 |
| src/pretalx/orga/forms/schedule.py                                         |      119 |       30 |       14 |        2 |     71% |42->exit, 204, 219, 222-224, 227-229, 232-234, 237-238, 241-242, 245-246, 249-250, 253-254, 257-258, 261, 264, 267, 270, 273, 276, 279 |
| src/pretalx/orga/forms/speaker.py                                          |       46 |        4 |        2 |        1 |     90% |74, 82, 85, 93 |
| src/pretalx/orga/forms/submission.py                                       |      178 |       17 |       78 |       15 |     87% |68-70, 110->112, 115, 118->126, 138, 142, 153, 162, 169, 178, 187->189, 196, 220-222, 278, 365-366 |
| src/pretalx/orga/forms/widgets.py                                          |       47 |        2 |        0 |        0 |     96% |     96-97 |
| src/pretalx/orga/permissions.py                                            |        3 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/phrases.py                                                |       11 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/receivers.py                                              |       16 |        2 |        4 |        2 |     80% |    17, 29 |
| src/pretalx/orga/rules.py                                                  |        8 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/signals.py                                                |       28 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/cfp.py                                             |       84 |        4 |        6 |        3 |     92% |70, 92, 259, 261 |
| src/pretalx/orga/tables/mail.py                                            |       36 |        3 |        2 |        0 |     87% |   110-112 |
| src/pretalx/orga/tables/organiser.py                                       |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/schedule.py                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/tables/speaker.py                                         |       58 |        4 |        4 |        2 |     90% |42, 45, 51, 150 |
| src/pretalx/orga/tables/submission.py                                      |      173 |       40 |       60 |        6 |     68% |120->122, 131, 159, 162, 168, 239, 241-242, 248->250, 277-279, 320, 331-335, 338-375 |
| src/pretalx/orga/templatetags/formsets.py                                  |       16 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/orga\_edit\_link.py                          |       10 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/templatetags/platform\_icons.py                           |        9 |        1 |        2 |        1 |     82% |        16 |
| src/pretalx/orga/templatetags/querystring.py                               |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/orga/templatetags/review\_score.py                             |       17 |        1 |        8 |        1 |     92% |        25 |
| src/pretalx/orga/utils/i18n.py                                             |       39 |        5 |       12 |        2 |     82% |183-184, 210-212 |
| src/pretalx/orga/views/auth.py                                             |       59 |        2 |        8 |        2 |     94% |    41, 53 |
| src/pretalx/orga/views/cards.py                                            |       17 |        0 |        2 |        0 |    100% |           |
| src/pretalx/orga/views/cfp.py                                              |      733 |       63 |      214 |       43 |     88% |97, 100, 111-112, 116->120, 160, 168, 192, 196, 199->193, 221, 228, 230, 232, 234-236, 266-272, 290, 300->303, 304, 308-319, 365, 374, 413->407, 415->407, 491, 557, 609-610, 693, 694->696, 698->700, 700->703, 764, 777, 825, 827, 886->888, 900->899, 932-937, 956-957, 1004->1003, 1016-1017, 1046-1047, 1050, 1054, 1072, 1091, 1142, 1155, 1194-1200 |
| src/pretalx/orga/views/dashboard.py                                        |      161 |       28 |       46 |        9 |     78% |31-43, 79, 108-114, 136-137, 156-167, 219, 236-239, 285-286, 295->307, 352-353, 362-369 |
| src/pretalx/orga/views/event.py                                            |      428 |       28 |      114 |       25 |     89% |154-155, 203, 270, 316, 356, 358->363, 387, 392->390, 407, 415, 419, 425, 455, 459->457, 461, 471-472, 475-479, 482, 582-588, 656, 676, 699-700, 724->723, 727->729, 730, 773->778 |
| src/pretalx/orga/views/mails.py                                            |      353 |       47 |       74 |       14 |     82% |56-57, 186-188, 198, 207-209, 259-265, 337-339, 373->381, 377, 403, 408-409, 436, 460, 466-511, 538-540, 555, 561, 579 |
| src/pretalx/orga/views/organiser.py                                        |      311 |       37 |       56 |        8 |     82% |118-120, 141-142, 157-158, 294-295, 336, 383, 396, 398-414, 428, 431, 436, 441-460, 463, 466-470, 473-475 |
| src/pretalx/orga/views/person.py                                           |      120 |       20 |       30 |        5 |     81% |77-86, 90-97, 99-107, 156, 165, 181-182 |
| src/pretalx/orga/views/plugins.py                                          |       36 |        0 |        6 |        0 |    100% |           |
| src/pretalx/orga/views/review.py                                           |      521 |       65 |      114 |       17 |     84% |87, 90-93, 95-98, 250->252, 252->258, 293->exit, 314-315, 317-323, 356, 365-370, 375, 381-386, 391, 400-414, 436, 450-457, 498-499, 510-511, 522->535, 539, 721-722, 733-736, 738-742, 903-904, 965-976, 991, 1021-1022 |
| src/pretalx/orga/views/schedule.py                                         |      300 |       29 |       52 |        9 |     86% |52->59, 121-122, 165-169, 317, 318->321, 330, 360, 383, 395, 405, 415-446, 464, 506, 571-578 |
| src/pretalx/orga/views/speaker.py                                          |      199 |       10 |       20 |        5 |     92% |93-105, 107-110, 234, 306, 369-370 |
| src/pretalx/orga/views/submission.py                                       |      674 |       36 |      120 |       21 |     92% |199-203, 223-225, 228, 245-251, 338->346, 428, 436, 460, 548, 551->545, 588, 611->622, 623, 630->642, 640->642, 700, 753->exit, 755, 825-826, 859->869, 911, 962, 989, 1233, 1237, 1241, 1248-1254, 1277-1278, 1280-1281 |
| src/pretalx/orga/views/typeahead.py                                        |       59 |       16 |       16 |        5 |     64% |45, 54, 63, 104-109, 114, 119-131, 154, 193-196 |
| src/pretalx/person/apps.py                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/exporters.py                                            |       23 |        1 |        4 |        1 |     93% |        33 |
| src/pretalx/person/forms/auth.py                                           |       43 |        2 |       10 |        2 |     92% |    41, 48 |
| src/pretalx/person/forms/auth\_token.py                                    |       43 |       17 |       10 |        0 |     53% |61-63, 76-95 |
| src/pretalx/person/forms/information.py                                    |       21 |        1 |        2 |        1 |     91% |        18 |
| src/pretalx/person/forms/profile.py                                        |      190 |       31 |       70 |       14 |     79% |65->67, 89-90, 91->101, 111->exit, 132->134, 145, 160, 162, 164, 178, 209->exit, 216, 232-238, 241-242, 294->exit, 312, 338-343, 346-355 |
| src/pretalx/person/forms/user.py                                           |       87 |        6 |       26 |        4 |     91% |80, 83-84, 113, 125, 170 |
| src/pretalx/person/models/auth\_token.py                                   |       73 |       11 |       20 |        0 |     82% |101, 104, 146-155 |
| src/pretalx/person/models/information.py                                   |       33 |        0 |        2 |        1 |     97% |    20->22 |
| src/pretalx/person/models/preferences.py                                   |       41 |        5 |       18 |        3 |     83% |47-53, 92, 109->112 |
| src/pretalx/person/models/profile.py                                       |       58 |        2 |        6 |        3 |     92% |114, 135, 141->exit, 146->exit, 151->157 |
| src/pretalx/person/models/user.py                                          |      270 |        7 |       52 |        8 |     95% |85, 243->247, 253->256, 261, 274, 375->377, 380, 448-450, 475->488 |
| src/pretalx/person/rules.py                                                |       33 |        2 |       10 |        2 |     91% |    44, 46 |
| src/pretalx/person/services.py                                             |        9 |        0 |        2 |        1 |     91% |    20->22 |
| src/pretalx/person/signals.py                                              |        8 |        0 |        0 |        0 |    100% |           |
| src/pretalx/person/tasks.py                                                |       47 |       17 |       14 |        1 |     57% |     43-65 |
| src/pretalx/schedule/apps.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/ascii.py                                              |      127 |       30 |       54 |        8 |     71% |66->69, 72->75, 77-81, 92-96, 97->exit, 102-114, 144, 147-168, 182 |
| src/pretalx/schedule/exporters.py                                          |      119 |        4 |       22 |        0 |     96% |   336-342 |
| src/pretalx/schedule/forms.py                                              |       54 |        0 |        8 |        1 |     98% |    65->68 |
| src/pretalx/schedule/ical.py                                               |       37 |        2 |        4 |        0 |     95% |     24-25 |
| src/pretalx/schedule/models/availability.py                                |       88 |        1 |       34 |        1 |     98% |55, 76->79 |
| src/pretalx/schedule/models/room.py                                        |       44 |        3 |        4 |        2 |     90% |94, 101, 104 |
| src/pretalx/schedule/models/schedule.py                                    |      207 |       30 |       70 |        8 |     83% |148-189, 236->238, 280, 284, 354, 366-374, 385-393, 420->422, 520 |
| src/pretalx/schedule/models/slot.py                                        |      129 |        5 |       22 |        2 |     94% |209-216, 227 |
| src/pretalx/schedule/notifications.py                                      |       20 |        0 |        4 |        0 |    100% |           |
| src/pretalx/schedule/phrases.py                                            |       14 |        0 |        0 |        0 |    100% |           |
| src/pretalx/schedule/services.py                                           |      225 |        6 |       90 |       11 |     94% |71->73, 76->78, 78->80, 80->82, 82->75, 121-123, 127->125, 138->130, 141->143, 143->146, 335, 428-429 |
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
| src/pretalx/submission/forms/submission.py                                 |      250 |       31 |      106 |       16 |     85% |113, 156, 170, 175->exit, 180, 220, 224-225, 228, 235-242, 265->267, 429, 431-437, 479-492, 494-497, 504, 518-521, 526 |
| src/pretalx/submission/forms/tag.py                                        |       21 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/icons.py                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/access\_code.py                              |       56 |        0 |        4 |        0 |    100% |           |
| src/pretalx/submission/models/cfp.py                                       |       82 |        0 |        8 |        0 |    100% |           |
| src/pretalx/submission/models/comment.py                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/feedback.py                                  |       20 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/question.py                                  |      274 |       23 |       66 |        7 |     86% |41->44, 389, 393-394, 412-416, 422, 464->467, 528-534, 606, 615-617, 648->655, 650, 653-654 |
| src/pretalx/submission/models/resource.py                                  |       39 |        0 |        8 |        2 |     96% |62->exit, 69->exit |
| src/pretalx/submission/models/review.py                                    |      125 |       11 |       26 |        7 |     85% |55-56, 59->exit, 72, 76-78, 95, 98->102, 103, 108, 185, 301 |
| src/pretalx/submission/models/submission.py                                |      535 |       38 |      126 |       15 |     90% |394-396, 472, 517->537, 525, 529-531, 544-545, 645->651, 667-668, 766->exit, 773, 789-791, 794, 872-887, 942, 974, 1020-1022, 1033-1038, 1136->exit, 1155-1167, 1184->exit, 1246 |
| src/pretalx/submission/models/tag.py                                       |       24 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/models/track.py                                     |       34 |        1 |        0 |        0 |     97% |        89 |
| src/pretalx/submission/models/type.py                                      |       39 |        1 |        4 |        1 |     95% |        20 |
| src/pretalx/submission/phrases.py                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/rules.py                                            |      203 |       13 |       56 |        7 |     92% |13-14, 30-31, 174-175, 189, 196, 227, 239, 268, 345, 360 |
| src/pretalx/submission/signals.py                                          |        5 |        0 |        0 |        0 |    100% |           |
| src/pretalx/submission/tasks.py                                            |       69 |       12 |       16 |        4 |     81% |29-30, 34, 72, 81-83, 91-92, 99-101 |
| src/tests/agenda/test\_agenda\_permissions.py                              |       22 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_schedule\_export.py                         |      345 |        0 |        8 |        0 |    100% |           |
| src/tests/agenda/test\_agenda\_widget.py                                   |       41 |        0 |        2 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_featured.py                           |       57 |        0 |        4 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_feedback.py                           |       63 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_schedule.py                           |      243 |        0 |       20 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_talks.py                              |      197 |        0 |        0 |        0 |    100% |           |
| src/tests/agenda/views/test\_agenda\_widget.py                             |       42 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_access\_code.py                                   |      116 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_answers.py                                        |      134 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_events.py                                         |       45 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_feedback.py                                       |      167 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_mail.py                                           |      108 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_questions.py                                      |      478 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_reviews.py                                        |      372 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_rooms.py                                          |      205 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_root.py                                           |       13 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_schedule.py                                       |      498 |        0 |        6 |        0 |    100% |           |
| src/tests/api/test\_api\_speaker\_information.py                           |      141 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_speakers.py                                       |      299 |        0 |        4 |        0 |    100% |           |
| src/tests/api/test\_api\_submissions.py                                    |      906 |        0 |        2 |        0 |    100% |           |
| src/tests/api/test\_api\_teams.py                                          |      208 |        0 |        0 |        0 |    100% |           |
| src/tests/api/test\_api\_upload.py                                         |       30 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/test\_cfp\_flow.py                                           |      134 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_auth.py                                     |      139 |        0 |        2 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_base.py                                     |       70 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_user.py                                     |      800 |        0 |       12 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_view\_flow.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/tests/cfp/views/test\_cfp\_wizard.py                                   |      445 |        0 |       20 |        0 |    100% |           |
| src/tests/common/forms/test\_cfp\_forms\_utils.py                          |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/forms/test\_cfp\_forms\_validators.py                     |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/forms/test\_common\_form\_widgets.py                      |       50 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_log.py                                         |       43 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_middleware.py                                  |       57 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_cfp\_serialize.py                                   |        5 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_cache.py                                    |       39 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_checks.py                                   |       16 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_console.py                                  |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_css.py                                      |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_exporter.py                                 |        6 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_forms\_utils.py                             |        9 |        0 |        2 |        0 |    100% |           |
| src/tests/common/test\_common\_mail.py                                     |       62 |        0 |        0 |        0 |    100% |           |
| src/tests/common/test\_common\_management\_commands.py                     |       78 |        0 |        0 |        0 |    100% |           |
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
| src/tests/conftest.py                                                      |      540 |        0 |       12 |        0 |    100% |           |
| src/tests/dummy\_app.py                                                    |       13 |        0 |        0 |        0 |    100% |           |
| src/tests/dummy\_signals.py                                                |       52 |        0 |        8 |        0 |    100% |           |
| src/tests/event/test\_event\_model.py                                      |      170 |        0 |        0 |        0 |    100% |           |
| src/tests/event/test\_event\_services.py                                   |       59 |        0 |        0 |        0 |    100% |           |
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
| src/tests/orga/views/test\_orga\_views\_admin.py                           |       87 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_cfp.py                             |      784 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_dashboard.py                       |      112 |        0 |       40 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_event.py                           |      461 |        0 |        0 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_mail.py                            |      396 |        0 |       10 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_organiser.py                       |      339 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_person.py                          |       44 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_review.py                          |      373 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_schedule.py                        |      327 |        0 |        4 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_speaker.py                         |      240 |        0 |        2 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission.py                      |      681 |        0 |        8 |        0 |    100% |           |
| src/tests/orga/views/test\_orga\_views\_submission\_cards.py               |       14 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_auth\_token\_model.py                               |       11 |        0 |        0 |        0 |    100% |           |
| src/tests/person/test\_information\_model.py                               |        7 |        0 |        0 |        0 |    100% |           |
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
| src/tests/submission/test\_question\_model.py                              |      150 |        0 |       10 |        0 |    100% |           |
| src/tests/submission/test\_review\_model.py                                |       19 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_model.py                            |      265 |        0 |        2 |        0 |    100% |           |
| src/tests/submission/test\_submission\_permissions.py                      |       47 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_tasks.py                            |       64 |        0 |        0 |        0 |    100% |           |
| src/tests/submission/test\_submission\_type\_model.py                      |       21 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                                                                  | **34606** | **1929** | **5498** |  **774** | **92%** |           |


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