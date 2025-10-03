def is_form_bound(request, form_name, form_param="form"):
    return request.method == "POST" and request.POST.get(form_param) == form_name
