# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def create_resource(
    submission, *, user, description, link="", resource=None, is_public=True
):
    old_data = submission.get_instance_data()
    obj = submission.resources.create(
        link=link or "", resource=resource, description=description, is_public=is_public
    )
    if hasattr(submission, "_prefetched_objects_cache"):
        submission._prefetched_objects_cache.pop("resources", None)  # noqa: SLF001 -- Django internal
    new_data = submission.get_instance_data()
    submission.log_action(
        ".update", person=user, orga=True, old_data=old_data, new_data=new_data
    )
    return obj


def delete_resource(resource, *, user):
    submission = resource.submission
    old_data = submission.get_instance_data()
    resource.delete()
    if hasattr(submission, "_prefetched_objects_cache"):
        submission._prefetched_objects_cache.pop("resources", None)  # noqa: SLF001 -- Django internal
    new_data = submission.get_instance_data()
    submission.log_action(
        ".update", person=user, orga=True, old_data=old_data, new_data=new_data
    )
