import requests
import time
import re
import dateparser
# import argparse
import json
import sys
class youtube ():
    def __init__(self, url, limit):
        self.YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'
        self.USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'
        self.SORT_BY_POPULAR = 0
        self.SORT_BY_RECENT = 1
        self.YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
        self.YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
        self.INDENT = 4
        self.url = url
        self.Limit = limit

    def get_comments(self, youtube_url, sort_by=1, language=None, sleep=.1):
        session = requests.Session()
        response = session.get(youtube_url)

        html = response.text
        ytcfg = json.loads(self.regex_search(html, self.YT_CFG_RE, default=''))
        if not ytcfg:
            return  # Unable to extract configuration
        if language:
            ytcfg['INNERTUBE_CONTEXT']['client']['hl'] = language

        data = json.loads(self.regex_search(html, self.YT_INITIAL_DATA_RE, default=''))

        section = next(self.search_dict(data, 'itemSectionRenderer'), None)
        renderer = next(self.search_dict(section, 'continuationItemRenderer'), None) if section else None
        if not renderer:
            # Comments disabled?
            return

        sort_menu = next(self.search_dict(data, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
        if not sort_menu or sort_by >= len(sort_menu):
            raise RuntimeError('Failed to set sorting')
        continuations = [sort_menu[sort_by]['serviceEndpoint']]

        while continuations:
            continuation = continuations.pop()
            response = self.ajax_request(continuation, ytcfg, session)

            if not response:
                break

            error = next(self.search_dict(response, 'externalErrorMessage'), None)
            if error:
                raise RuntimeError('Error returned from server: ' + error)

            actions = list(self.search_dict(response, 'reloadContinuationItemsCommand')) + \
                    list(self.search_dict(response, 'appendContinuationItemsAction'))
            for action in actions:
                for item in action.get('continuationItems', []):
                    if action['targetId'] in ['comments-section', 'engagement-panel-comments-section']:
                        # Process continuations for comments and replies.
                        continuations[:0] = [ep for ep in self.search_dict(item, 'continuationEndpoint')]
                    if action['targetId'].startswith('comment-replies-item') and 'continuationItemRenderer' in item:
                        # Process the 'Show more replies' button
                        continuations.append(next(self.search_dict(item, 'buttonRenderer'))['command'])

            for comment in reversed(list(self.search_dict(response, 'commentRenderer'))):
                result = {'cid': comment['commentId'],
                        'text': ''.join([c['text'] for c in comment['contentText'].get('runs', [])]),}
                        # 'time': comment['publishedTimeText']['runs'][0]['text'],
                        # 'author': comment.get('authorText', {}).get('simpleText', ''),
                        # 'channel': comment['authorEndpoint']['browseEndpoint'].get('browseId', ''),
                        # 'votes': comment.get('voteCount', {}).get('simpleText', '0'),
                        # 'photo': comment['authorThumbnail']['thumbnails'][-1]['url'],
                        # 'heart': next(self.search_dict(comment, 'isHearted'), False),
                        # 'reply': '.' in comment['commentId']}

                try:
                    result['time_parsed'] = dateparser.parse(result['time'].split('(')[0].strip()).timestamp()
                except AttributeError:
                    pass

                paid = (
                    comment.get('paidCommentChipRenderer', {})
                    .get('pdgCommentChipRenderer', {})
                    .get('chipText', {})
                    .get('simpleText')
                )
                if paid:
                    result['paid'] = paid

                yield result
            time.sleep(sleep)

    @staticmethod
    def regex_search(text, pattern, group=1, default=None):
        match = re.search(pattern, text)
        return match.group(group) if match else default

    @staticmethod
    def search_dict(partial, search_key):
        stack = [partial]
        while stack:
            current_item = stack.pop()
            if isinstance(current_item, dict):
                for key, value in current_item.items():
                    if key == search_key:
                        yield value
                    else:
                        stack.append(value)
            elif isinstance(current_item, list):
                for value in current_item:
                    stack.append(value)

    @staticmethod
    def ajax_request(endpoint, ytcfg, session, retries=5, sleep=20):
        url = 'https://www.youtube.com' + endpoint['commandMetadata']['webCommandMetadata']['apiUrl']

        data = {'context': ytcfg['INNERTUBE_CONTEXT'],
                'continuation': endpoint['continuationCommand']['token']}

        for _ in range(retries):
            response = session.post(url, params={'key': ytcfg['INNERTUBE_API_KEY']}, json=data)
            if response.status_code == 200:
                return response.json()
            if response.status_code in [403, 413]:
                return {}
            else:
                time.sleep(sleep)

    @staticmethod
    def to_json(comment, indent=None):
        comment_str = json.dumps(comment, ensure_ascii=False, indent=indent)
        if indent is None:
            return comment_str
        padding = ' ' * (2 * indent) if indent else ''
        return ''.join(padding + line for line in comment_str.splitlines(True))
    def main(self):
        # parser = argparse.ArgumentParser(add_help=False,
        #                                 description='Download Youtube comments without using the Youtube API')
        # parser.add_argument('--url', '-u', help='Youtube URL for which to download the comments')
        # parser.add_argument('--limit', '-l', type=int, help='Limit the number of comments')
        try:
            youtube_url = self.url
            limit = self.Limit
            real_dic = []
            pretty = None  # args.pretty      
            # if not youtube_url:
            #     parser.print_usage()
            #     raise ValueError('you need to specify a Youtube ID/URL')

            print('Downloading Youtube comments for', youtube_url)
            generator = (

                self.get_comments(youtube_url)  # args.sort, args.language
            )
            count = 1
            comment_dic = {}
            comment = next(generator, None)
            while comment:
                comment_str = self.to_json(comment, indent=self.INDENT if pretty else None)
                comment = None if limit and count >= limit else next(generator,
                                                                    None)  # Note that this is the next comment
                comment_str = comment_str + ',' if pretty and comment is not None else comment_str
                W = comment_str.decode('utf-8') if isinstance(comment_str, bytes) else comment_str
                res = json.loads(W)
                comment_dic.update(res)
                comment_dic["_id"] = comment_dic.pop("cid")
                real_dic.append(comment_dic.copy())
                count += 1
        except Exception as e:
            print('Error:', str(e))
            sys.exit(1)
        return real_dic
print(youtube('https://www.youtube.com/watch?v=kJQP7kiw5Fk',10000).main())