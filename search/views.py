# -*- coding: utf-8 -*-
import re
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from data_center.models import Course, Department
from data_center.const import DEPT_CHOICE, GEC_CHOICE, GE_CHOICE, T_YEAR, C_TERM
from django.views.decorators.cache import cache_page
from django import forms

import requests
import bs4
from haystack.query import SearchQuerySet
from haystack.inputs import AutoQuery

SYM_URL = 'http://class-qry.acad.ncku.edu.tw/syllabus/online_display.php'

def group_words(s):
    """Split Chinese token for better search result"""
    regex = []

    # Match a whole word:
    regex += [ur'\w+']

    # Match a single CJK character:
    regex += [ur'[\u4e00-\ufaff]']

    # Match one of anything else, except for spaces:
    regex += [ur'[^\s]']

    regex = "|".join(regex)
    r = re.compile(regex)

    return r.findall(s)


def search(request):
    result = {}
    q = request.GET.get('q', '')
    q = ' '.join(group_words(q))
    page = request.GET.get('page', '')
    size = request.GET.get('size', '')
    code = request.GET.get('code', '')
    dept_required = request.GET.get('dept_required', '')
    sortby_param = request.GET.get('sort', '')
    reverse_param = request.GET.get('reverse', '')

    page_size = size or 10
    sortby = sortby_param or 'time_token'
    reverse = True if reverse_param == 'true' else False
    rev_sortby = '-' + sortby if reverse else sortby

    courses = SearchQuerySet()

    if dept_required:
        try:
            courses = Department.objects.get(
                dept_name=dept_required).required_course.all()
        except:
            pass
        if courses:
            result['type'] = 'required'
            page_size = courses.count()
    else:
        courses = courses.filter(content=AutoQuery(q))
        if code:
            courses = courses.filter(code__contains=code)

        if courses.count() > 300:
            return HttpResponse('TMD')  # Too many detail

        courses = Course.objects.filter(pk__in=[c.pk for c in courses])
        if code in ['A9']:
            core = request.GET.get('ge', '')
            print core
            if core:
                courses = courses.filter(ge__contains=core)

    courses = courses.order_by(rev_sortby)
    paginator = Paginator(courses, page_size)

    try:
        courses_page = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        courses_page = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        courses_page = paginator.page(paginator.num_pages)

    courses_list = courses_page.object_list. \
        values('id', 'no', 'eng_title', 'chi_title', 'note', 'objective',
               'time', 'time_token', 'teacher', 'room', 'credit',
               'prerequisite', 'ge', 'code')

    result['total'] = courses.count()
    result['page'] = courses_page.number
    result['courses'] = list(courses_list)
    result['page_size'] = page_size

    return JsonResponse(result)


@cache_page(60 * 60)
def syllabus(request, id):
    course = get_object_or_404(Course, id=id)
    if course is not None:
        clas_map = {'甲':'1', '乙':'2', '丙':'3'}
        if course.clas is not None and len(course.clas) > 0:
            clas = clas_map[course.clas.encode('utf8')]
        else:
            clas = ''
        url = SYM_URL + "?syear=0%s&sem=%s&co_no=%s&class_code=%s" % (T_YEAR, C_TERM, course.serial, clas)

        html = requests.get(url).content.decode('big5', 'ignore').encode('utf8', 'ignore').replace('<br>', '<br/>')
        print url

        soup = bs4.BeautifulSoup(html, 'html.parser')
        course_outline = soup.find('div', { 'id': 'container' })
        [x.extract() for x in course_outline.find_all('div', { 'id': 'header' })]
        course.syllabus = str(course_outline.contents[2])

    return render(request, 'syllabus.html',
                  {'course': course, 'syllabus_path': request.path})


def hit(request, id):
    course = get_object_or_404(Course, id=id)
    course.hit += 1
    course.save()
    return HttpResponse('')


def generate_dept_required_choice():
    choices = (('', '---'),)
    departments = Department.objects.all()
    for department in departments:
        dept_name = department.dept_name

        yr_translate_map = {}
        for i in range(0, 8):
            yr_translate_map[T_YEAR - i] = ' ' + str(i + 1) + '年級'

        year = yr_translate_map. \
            get(int(dept_name[4:-2]), '')

        degree = {'B': '大學部', 'D': '博士班', 'M': '碩士班', 'P': '專班'}. \
            get(dept_name[-2], '')
        chi_dept_name = degree

        if dept_name[-2] == 'B':
            chi_dept_name += year
            chi_dept_name += {'BA': '甲班', 'BB': '乙班', 'BC': '丙班'}. \
                get(dept_name[-2:], '')

        choices += ((dept_name, chi_dept_name),)
    return sorted(choices, key = lambda x: x[1])


class CourseSearchForm(forms.Form):
    DEPT_REQUIRED_CHOICE = generate_dept_required_choice()
    q = forms.CharField(label='關鍵字', required=False)
    code = forms.ChoiceField(label='開課代號', choices=DEPT_CHOICE, required=False)
    ge = forms.ChoiceField(label='向度', choices=GE_CHOICE, required=False)
    gec = forms.ChoiceField(label='向度', choices=GEC_CHOICE, required=False)
    dept_required = forms.ChoiceField(
        label='必選修', choices=DEPT_REQUIRED_CHOICE, required=False)


def table(request):
    render_data = {}
    render_data['search_filter'] = CourseSearchForm(request.GET)
    return render(request, 'table.html', render_data)
