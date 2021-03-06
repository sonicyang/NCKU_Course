from django.core.management.base import BaseCommand

from crawler.crawler import crawl_course, crawl_dept
try:
    from crawler.decaptcha import Entrance, DecaptchaFailure
except ImportError:
    Entrance = None
from data_center.models import Course, Department


def get_auth_pair(url):
    if Entrance is not None:
        try:
            return Entrance(url).get_ticket()
        except DecaptchaFailure:
            print 'Automated decaptcha failed.'
    else:
        print 'crawler.decaptcha not available (requires tesseract >= 3.03).'
    print 'Please provide valid ACIXSTORE and auth_num from'
    print url
    ACIXSTORE = raw_input('ACIXSTORE: ')
    auth_num = raw_input('auth_num: ')
    return ACIXSTORE, auth_num


class Command(BaseCommand):
    args = ''
    help = 'Help crawl the course data from NCKU.'

    def handle(self, *args, **kwargs):
        if len(args) == 0:
            crawl_course()

            crawl_dept()
            # elapsed_time = time.time() - start_time
            # print 'Total %.3f second used.' % elapsed_time
        if len(args) == 1:
            if args[0] == 'clear':
                Course.objects.all().delete()
                Department.objects.all().delete()
