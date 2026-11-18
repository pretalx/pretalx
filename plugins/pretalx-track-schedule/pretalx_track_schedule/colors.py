"""Session colours from the answers to one per-proposal choice question
(e.g. "Difficulty"), set up on the plugin's settings page."""

from .models import ColorSettings, OptionColor

CHOICE_VARIANTS = ("choices", "multiple_choice")


def colour_question(event):
    settings = (
        ColorSettings.objects.filter(event=event, question__isnull=False)
        .select_related("question")
        .first()
    )
    return settings.question if settings else None


def legend_and_colours(event, submission_ids):
    """([(label, colour)], {submission_id: (label, colour)}). A session with
    several answers (multiple choice) takes its first option that has a
    colour; sessions without an answer get none and keep their track colour."""
    from pretalx.submission.models import Answer

    question = colour_question(event)
    if question is None:
        return [], {}
    colours = {
        oc.option_id: oc.color
        for oc in OptionColor.objects.filter(option__question=question)
    }
    options = [
        option
        for option in question.options.all().order_by("position", "id")
        if option.pk in colours
    ]
    order = {option.pk: index for index, option in enumerate(options)}
    legend = [(str(option.answer), colours[option.pk]) for option in options]
    result = {}
    answers = Answer.objects.filter(
        question=question, submission_id__in=submission_ids
    ).prefetch_related("options")
    for answer in answers:
        coloured = sorted(
            (o for o in answer.options.all() if o.pk in colours),
            key=lambda o: order[o.pk],
        )
        if coloured:
            option = coloured[0]
            result[answer.submission_id] = (str(option.answer), colours[option.pk])
    return legend, result
