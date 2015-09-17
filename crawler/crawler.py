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

BASE_URL = 'http://class-qry.acad.ncku.edu.tw/qry/'
DEPT_URL = 'http://class-qry.acad.ncku.edu.tw/qry/qry001.php?dept_no='
URL = 'https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/6/6.2/6.2.3/JH623002.php'  # noqa
YS = '104|10'
cond = 'a'
T_YEAR = 104
C_TERM = 10


class Course_Struct(object):
    def __init__(self):
        self.dept = None
        self.no = None
        self.serial = None
        self.ge = None
        self.clas = None
        self.time = None
        self.note = None
        self.objective = None
        self.prerequisite = None
        self.credit = None
        self.limit = None

    def __str__(self):
        return str((self.dept, self.no, self.serial, self.time))


def dept_2_html(dept, ACIXSTORE, auth_num):
    try:
        r = requests.post(dept_url,
                          data={
                              'SEL_FUNC': 'DEP',
                              'ACIXSTORE': ACIXSTORE,
                              'T_YEAR': T_YEAR,
                              'C_TERM': C_TERM,
                              'DEPT': dept,
                              'auth_num': auth_num})
        return r.content.decode('big5', 'ignore').encode('utf8', 'ignore')
    except:
        print traceback.format_exc()
        print dept
        return 'QAQ, what can I do?'


def cou_code_2_html(cou_code, ACIXSTORE, auth_num):
    try:
        r = requests.post(URL,
                          data={
                              'ACIXSTORE': ACIXSTORE,
                              'YS': YS,
                              'cond': cond,
                              'cou_code': cou_code,
                              'auth_num': auth_num})
        return r.content.decode('big5', 'ignore').encode('utf8', 'ignore')
    except:
        print traceback.format_exc()
        print cou_code
        return 'QAQ, what can I do?'


def reterieve_html(url):
    try:
        r = requests.get(url)
        return r.content
    except:
        print traceback.format_exc()
        return 'Failed to crawl :' + str(url)


def syllabus_2_html(ACIXSTORE, course):
    url = 'https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/common/Syllabus/1.php?ACIXSTORE=%s&c_key=%s' % (ACIXSTORE, course.no.replace(' ', '%20'))  # noqa
    try:
        while True:
            r = requests.get(url)
            html = r.content.decode('big5', 'ignore').encode('utf8', 'ignore')
            soup = bs4.BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')
            if tables:
                trs = tables[0].find_all('tr')
                break
            else:
                continue
        for i in range(2, 5):
            trs[i].find_all('td')[1]['colspan'] = 5
        course.chi_title = trs[2].find_all('td')[1].get_text()
        course.eng_title = trs[3].find_all('td')[1].get_text()
        course.teacher = trs[4].find_all('td')[1].get_text()
        course.room = trs[5].find_all('td')[3].get_text()
        course.syllabus = trim_syllabus(ACIXSTORE, soup)
        course.save()
    except:
        print traceback.format_exc()
        print course
        return 'QAQ, what can I do?'


def trim_syllabus(ACIXSTORE, soup):
    href_garbage = '?ACIXSTORE=%s' % ACIXSTORE
    host = 'https://www.ccxp.nthu.edu.tw'
    # Remove width
    for tag in soup.find_all():
        if 'width' in tag:
            del tag['width']
    # Replace link
    for a in soup.find_all('a'):
        href = a.get('href', '').replace(href_garbage, '').replace(' ', '%20')
        # Make relative path to absolute path
        if 'http' not in href:
            href = host + href
        a['href'] = href
        a['target'] = '_blank'
    syllabus = ''.join(map(unicode, soup.body.contents))
    syllabus = syllabus.replace('</br></br></br></br></br>', '')
    syllabus = syllabus.replace('<br><br><br><br><br>', '')
    return syllabus


def trim_element(element):
    return element.get_text().strip()


def get_dept_list():
    html = reterieve_html(BASE_URL)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    dept_divs = soup.find_all('div', class_='dept')
    dept_a_s = map(lambda x: x.find('a'), dept_divs)
    dept_names = map(lambda x: x.get_text().strip()[2:4], dept_a_s)

    return dept_names


def collect_course_info(tr):
    tds = tr.find_all('td')

    course = Course_Struct()

    course.dept = trim_element(tds[1])
    course.no = trim_element(tds[2])
    course.serial = trim_element(tds[3])
    course.clas = trim_element(tds[4])
    course.ge = trim_element(tds[10])
    course.time = trim_element(tds[16])
    course.note = trim_element(tds[18])
    course.objective = ""
    course.prerequisite = trim_element(tds[19])

    course.credit = trim_element(tds[12])
    course.credit = int(course.credit) if course.credit.isdigit() else 0

    #XXX: limit should be sum up of selected and vacant slot
    course.limit = trim_element(tds[14])
    course.limit = int(course.limit) if course.limit.isdigit() else 0

    return course


def archive_courses(courses):
    for course_it in courses:
        course, create = Course.objects.get_or_create(no=course_it.dept + course_it.no)

        course.dept = course_it.dept
        course.serial = course_it.serial
        course.clas = course_it.serial

        course.credit = course_it.credit
        course.time = course_it.time
        course.time_token = get_token(course_it.time)
        course.limit = course_it.limit
        course.note = course_it.note
        course.objective = course_it.objective
        course.prerequisite = course_it.prerequisite
        course.ge = course_it.ge
        course.save()


def crawl_dept_courses(dept_code):
    html = reterieve_html(DEPT_URL + dept_code)
    soup = bs4.BeautifulSoup(html, 'html.parser')

    # dept_name =

    class_list = ['course_y1', 'course_y2', 'course_y3', 'course_y4']

    courses_of_yrs = map(lambda x: soup.find_all('tr', class_=x), class_list)

    courses_trs = reduce(operator.add, courses_of_yrs, [])
    courses = map(collect_course_info, courses_trs)

    courses_without_no = filter(lambda x: x.no == '', courses)
    courses = filter(lambda x: x.no != '', courses)
    courses_needs_merge = filter(lambda x: x.serial in reduce(lambda y,z: y + [z.serial], courses, []), courses_without_no)

    for course in courses_needs_merge:
        print 'Merging: ' + course.serial
        target_course = filter(lambda x: (x.serial == course.serial) and (x.clas == course.clas), courses)[0]
        target_course.time += course.time

    for x in courses:
        print x

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

    # print 'Crawling syllabus...'
    # pool = threadpool.ThreadPool(50)
    # reqs = threadpool.makeRequests(
        # syllabus_2_html,
        # [([ACIXSTORE, course], {}) for course in Course.objects.all()]
    # )
    # [pool.putRequest(req) for req in reqs]
    # pool.wait()

    # print 'Total course information: %d' % Course.objects.count()


def crawl_dept_info(ACIXSTORE, auth_num, dept_code):
    html = dept_2_html(dept_code, ACIXSTORE, auth_num)
    soup = bs4.BeautifulSoup(html, 'html.parser')
    divs = soup.find_all('div', class_='newpage')

    for div in divs:
        # Get something like ``EE  103BA``
        dept_name = div.find_all('font')[0].get_text().strip()
        dept_name = dept_name.replace('B A', 'BA')
        dept_name = dept_name.replace('B B', 'BB')
        try:
            dept_name = re.search('\((.*?)\)', dept_name).group(1)
        except:
            # For all student (Not important for that dept.)
            continue

        trs = div.find_all('tr', bgcolor="#D8DAEB")
        department = Department.objects.get_or_create(
            dept_name=dept_name)[0]
        for tr in trs:
            tds = tr.find_all('td')
            cou_no = tds[0].get_text()
            try:
                course = Course.objects.get(no__contains=cou_no)
                department.required_course.add(course)
            except:
                print cou_no, 'gg'
        department.save()


def crawl_dept(ACIXSTORE, auth_num, dept_codes):
    threads = []

    for dept_code in dept_codes:
        t = Thread(
            target=crawl_dept_info,
            args=(ACIXSTORE, auth_num, dept_code)
        )
        threads.append(t)
        t.start()

    progress = progressbar.ProgressBar()
    for t in progress(threads):
        t.join()

    print 'Total department information: %d' % Department.objects.count()


def get_token(s):
    week_num_dict = {'1':'M', '2': 'T', '3': 'W', '4': 'R', '5': 'F', '6': 'S'}

    try:
        s = s + '['

        time_map = {}

        time_regex = re.compile('.\].+?\[')
        times = time_regex.findall(s)
        print times

        for time in times:
            time_map[week_num_dict[time[0]]] = []
            beg = int(time[3])
            end = int(time[-2])

            if end >= 5:
                end += 1

            for i in range(beg, end + 1):
                time_map[week_num_dict[time[1]]].append(i)

        print time_map


        # return week_dict[s[0]] + course_dict[s[1]] + s[2:]
        return s
    except:
        return ''
