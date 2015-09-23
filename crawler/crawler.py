# -*- coding: utf-8 -*-

import re
import bs4
import requests
import traceback
import progressbar
import threadpool
import operator
from threading import Thread
from data_center.models import Course, Department
from data_center.const import week_dict, course_dict
from data_center.const import T_YEAR, C_TERM

BASE_URL = 'http://class-qry.acad.ncku.edu.tw/qry/'
DEPT_URL = 'http://class-qry.acad.ncku.edu.tw/qry/qry001.php?dept_no='
SYM_URL = 'http://class-qry.acad.ncku.edu.tw/syllabus/online_display.php'
URL = 'https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/6/6.2/6.2.3/JH623002.php'  # noqa
cond = 'a'
YS = str(T_YEAR) + '|' + str(C_TERM)


class Course_Struct(object):
    def __init__(self):
        self.dept = None
        self.no = None
        self.serial = None
        self.ctitle = None
        self.clas = None
        self.time = None
        self.note = None
        self.objective = None
        self.prerequisite = None
        self.credit = None
        self.limit = None
        self.room = None
        self.teacher = None
        self.syllabus = None
        self.etitle = None
        self.optional = None

    def __str__(self):
        return str((self.dept, self.no, self.serial, self.time))


def reterieve_html(url):
    try:
        while True:
            r = requests.get(url)
            if r.status_code == 200:
                if 'SQLSTATE[08004]' not in r.content:
                    return r.content
            elif r.status_code == 404:
                return ''

    except:
        print traceback.format_exc()
        return 'Failed to crawl :' + str(url)


def crawl_syllabus(course):
    url = SYM_URL + "?syear=0%s&sem=%s&co_no=%s&class_code=%s" % (T_YEAR, C_TERM, course.serial, course.clas)

    html = reterieve_html(url).replace('<br>', '<br/>')
    soup = bs4.BeautifulSoup(html, 'html.parser')
    try:
        course.eng_title = soup.find('div', { 'id': 'header' }).find_all('span')[1].find_all('br')[1].get_text()
        if course.eng_title is None:
            course.eng_title = ""
        course_outline = soup.find('div', { 'id': 'container' })
        [x.extract() for x in course_outline.find_all('div', { 'id': 'header' })]
        course.syllabus = str(course_outline.contents[2])
    except:
        print course.dept + '-' + course.no
        print soup
        print "Error On Parsing Syllabus"


def trim_element(element):
    return element.get_text().strip(" \n\r")


def get_dept_list():
    html = reterieve_html(BASE_URL)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    dept_divs = soup.find_all('div', class_='dept')
    dept_a_s = map(lambda x: x.find('a'), dept_divs)
    dept_names = map(lambda x: x.get_text().strip()[2:4], dept_a_s)

    return dept_names

def get_inst_list():
    html = reterieve_html(BASE_URL)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    dept_divs = soup.find_all('div', class_='institute')
    dept_a_s = map(lambda x: x.find('a'), dept_divs)
    dept_names = map(lambda x: x.get_text().strip()[2:4], dept_a_s)

    return dept_names


def collect_course_info(tr):
    tds = tr.find_all('td')

    course = Course_Struct()

    course.dept = trim_element(tds[1])
    course.no = trim_element(tds[2])
    course.serial = trim_element(tds[3])
    course.clas = trim_element(tds[5])
    course.ctitle = trim_element(tds[10])
    course.time = trim_element(tds[16])
    course.note = trim_element(tds[18])
    course.objective = ""
    course.prerequisite = trim_element(tds[19])

    course.teacher = trim_element(tds[13])
    course.room = trim_element(tds[17])

    course.credit = trim_element(tds[12])
    course.credit = int(course.credit) if course.credit.isdigit() else 0

    course.optional = (False if trim_element(tds[11]).encode('utf8') == "必修" else True)

    #XXX: limit should be sum up of selected and vacant slot
    course.limit = trim_element(tds[14])
    course.limit = int(course.limit) if course.limit.isdigit() else 0

    return course


def archive_courses(courses):
    for course_it in courses:
        try:
            course, create = Course.objects.get_or_create(no=course_it.dept + '-' + course_it.no)

            course.dept = course_it.dept
            course.code = course_it.dept
            course.serial = course_it.serial
            course.clas = course_it.serial

            course.credit = course_it.credit
            course.time = parse_to_nthu(course_it.time)
            course.time_token = get_token(course.time)
            course.limit = course_it.limit
            course.note = course_it.note
            course.objective = course_it.objective
            course.prerequisite = course_it.prerequisite
            # course.ge = course_it.ge
            course.chi_title = course_it.ctitle


            course.teacher = course_it.teacher
            course.room = course_it.room
            course.save()

        except Exception as ex:
            print ex
            print course_it


def crawl_dept_courses(dept_code):
    html = reterieve_html(DEPT_URL + dept_code)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    # dept_name =

    class_list = []
    [class_list.append('course_y' + str(i)) for i in range(0, 8)]

    courses_of_yrs = map(lambda x: soup.find_all('tr', class_=x), class_list)

    courses_trs = reduce(operator.add, courses_of_yrs, [])
    courses = map(collect_course_info, courses_trs)

    courses_without_no = filter(lambda x: x.no == '', courses)
    courses = filter(lambda x: x.no != '', courses)
    courses_needs_merge = filter(lambda x: x.serial in reduce(lambda y,z: y + [z.serial], courses, []), courses_without_no)

    for course in courses_needs_merge:
        target_course = filter(lambda x: (x.serial == course.serial) and (x.clas == course.clas), courses)[0]
        target_course.time += course.time

    archive_courses(courses)


def crawl_course():
    threads = []

    for dept_code in get_dept_list():
        t = Thread(
            target=crawl_dept_courses,
            args=(dept_code,)
        )
        threads.append(t)
        t.start()

    progress = progressbar.ProgressBar()
    for t in progress(threads):
        t.join()


    threads = []
    for inst_code in get_inst_list():
        t = Thread(
            target=crawl_dept_courses,
            args=(inst_code,)
        )
        threads.append(t)
        t.start()

    progress = progressbar.ProgressBar()
    for t in progress(threads):
        t.join()

    print 'Crawling syllabus...'
    pool = threadpool.ThreadPool(50)
    reqs = threadpool.makeRequests(
        crawl_syllabus,
        [([course], {}) for course in Course.objects.all()]
    )
    [pool.putRequest(req) for req in reqs]
    pool.wait()

    print 'Total course information: %d' % Course.objects.count()


def crawl_dept_info(dept_code):
    if 'A' in dept_code:
        # GE courses won't be handle here
        return

    html = reterieve_html(DEPT_URL + dept_code)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    # dept_name =

    class_list = []
    [class_list.append('course_y' + str(i)) for i in range(1, 8)]

    courses_of_yrs = map(lambda x: soup.find_all('tr', class_=x), class_list)

    i = 0
    for course_tr in courses_of_yrs:
        i += 1

        if len(course_tr) != 0:
            courses = map(collect_course_info, course_tr)
            courses = filter(lambda x: x.no != '', courses)
            # courses = filter(lambda x: x.optional == True, courses)

            # Get something like ``EE  103BA``V

            clas_map = {'甲':'A', '乙':'B', '丙':'C'}
            for course in courses:
                if course.clas.encode('utf8') == '':
                    course.clas = '甲'.decode('utf8')
                for key, value in clas_map.iteritems():
                    if key in course.clas.encode('utf8'):
                        dept_name = (dept_code + '  ' + str(int(T_YEAR) - i + 1) + 'B' + value)

                        department = Department.objects.get_or_create(
                            dept_name=dept_name)[0]
                        try:
                            course_obj = Course.objects.filter(dept__contains=dept_code).get(no__contains=course.no)
                            department.required_course.add(course_obj)
                        except Exception as ex:
                            print ex
                            print dept_code, course.no, 'gg'
                        department.save()


def crawl_inst_info(dept_code):

    html = reterieve_html(DEPT_URL + dept_code)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    # dept_name =

    class_list = []
    [class_list.append('course_y' + str(i)) for i in range(1, 8)]

    courses_of_yrs = map(lambda x: soup.find_all('tr', class_=x), class_list)


    i = 0
    for course_tr in courses_of_yrs:
        i += 1

        if len(course_tr) != 0:
            courses = map(collect_course_info, course_tr)
            courses = filter(lambda x: x.no != '', courses)
            # courses = filter(lambda x: x.optional == True, courses)

            # Get something like ``EE  103BA``V

            for course in courses:
                dept_name = (dept_code + '  ' + str(int(T_YEAR) - i + 1) + 'MA')

                department = Department.objects.get_or_create(
                    dept_name=dept_name)[0]
                try:
                    course_obj = Course.objects.filter(dept__contains=dept_code).get(no__contains=course.no)
                    department.required_course.add(course_obj)
                except Exception as ex:
                    print ex
                    print dept_code, course.no, 'gg'
                department.save()


def crawl_dept():
    threads = []

    for dept_code in get_dept_list():
        t = Thread(
            target=crawl_dept_info,
            args=(dept_code,)
        )
        threads.append(t)
        t.start()

    progress = progressbar.ProgressBar()
    for t in progress(threads):
        t.join()

    threads = []
    for inst_code in get_inst_list():
        t = Thread(
            target=crawl_inst_info,
            args=(inst_code,)
        )
        threads.append(t)
        t.start()
        t.join()

    progress = progressbar.ProgressBar()
    for t in progress(threads):
        pass

    print 'Total department information: %d' % Department.objects.count()


def parse_to_nthu(s):
    week_num_dict = {'1':'M', '2': 'T', '3': 'W', '4': 'R', '5': 'F', '6': 'S', '7': 'U'}
    s = s + '['

    time_map = {'M':[], 'T':[], 'W':[], 'R':[], 'F':[], 'S':[], 'U':[] }

    time_regex = re.compile('.\].+?\[')
    times = time_regex.findall(s)

    for time in times:
        if 90 > ord(time[2]) > 57 :
            if ord(time[2]) == 78:
                beg = 5
            else:
                beg = ord(time[2]) - 54
        else:
            beg = int(time[2])
            if beg >= 5:
                beg += 1

        if 90 > ord(time[-2]) > 57 :
            if ord(time[-2]) == 78:
                end = 5
            else:
                end = ord(time[-2]) - 54
        else:
            end = int(time[-2])
            if end >= 5:
                end += 1


        for i in range(beg, end + 1):
            if i not in time_map[week_num_dict[time[0]]]:
                time_map[week_num_dict[time[0]]].append(i)

    ss = ""
    for key, value in time_map.iteritems():
        value.sort()
        for v in value:
            ss += str(key)
            if v < 5:
                ss += str(v)
            elif v == 5:
                ss += 'N'
            elif 11 > v > 5:
                ss += str(v - 1)
            else:
                ss += chr(int(v) + 54)

    return ss


def get_token(ss):

    try:
        return week_dict[ss[0]] + course_dict[ss[1]] + ss[2:]
    # return s
    except:
        return ''
