#--depends-on commands
#--depends-on config
#--require-config google-api-key

import re, urllib.parse
from src import EventManager, ModuleManager, utils

REGEX_YOUTUBE = re.compile("https?://(?:www.)?(?:youtu.be/|youtube.com/)\\S+", re.I)
REGEX_ISO8601 = re.compile("PT(\d+H)?(\d+M)?(\d+S)?", re.I)

URL_YOUTUBESEARCH = "https://www.googleapis.com/youtube/v3/search"
URL_YOUTUBEVIDEO = "https://www.googleapis.com/youtube/v3/videos"
URL_YOUTUBEPLAYLIST = "https://www.googleapis.com/youtube/v3/playlists"

URL_YOUTUBESHORT = "https://youtu.be/%s"
URL_VIDEO = "https://www.youtube.com/watch?v=%s"
URL_PLAYLIST = "https://www.youtube.com/playlist?list=%s"

ARROW_UP = "↑"
ARROW_DOWN = "↓"

@utils.export("channelset", utils.BoolSetting("auto-youtube",
    "Disable/Enable automatically getting info from youtube URLs"))
@utils.export("channelset", utils.BoolSetting("youtube-safesearch",
    "Turn safe search off/on"))
class Module(ModuleManager.BaseModule):
    def on_load(self):
        self.exports.add("search-youtube", self._search_youtube)

    def get_video_page(self, video_id, part):
        return utils.http.request(URL_YOUTUBEVIDEO, get_params={"part": part,
            "id": video_id, "key": self.bot.config["google-api-key"]},
            json=True)
    def video_details(self, video_id):
        snippet = self.get_video_page(video_id, "snippet")
        if snippet.data["items"]:
            snippet = snippet.data["items"][0]["snippet"]
            statistics = self.get_video_page(video_id, "statistics").data[
                "items"][0]["statistics"]
            content = self.get_video_page(video_id, "contentDetails").data[
                "items"][0]["contentDetails"]
            video_uploader = snippet["channelTitle"]
            video_title = snippet["title"]
            video_views = statistics["viewCount"]
            video_likes = statistics.get("likeCount")
            video_dislikes = statistics.get("dislikeCount")
            video_duration = content["duration"]
            video_opinions = ""
            if video_likes and video_dislikes:
                likes = utils.irc.color("%s%s" % (video_likes, ARROW_UP),
                    utils.consts.GREEN)
                dislikes = utils.irc.color("%s%s" %
                    (ARROW_DOWN, video_dislikes), utils.consts.RED)
                video_opinions = " (%s%s)" % (likes, dislikes)

            match = re.match(REGEX_ISO8601, video_duration)
            video_duration = ""
            video_duration += "%s:" % match.group(1)[:-1].zfill(2
                ) if match.group(1) else ""
            video_duration += "%s:" % match.group(2)[:-1].zfill(2
                ) if match.group(2) else "00:"
            video_duration += "%s" % match.group(3)[:-1].zfill(2
                ) if match.group(3) else "00"
            return "%s (%s) uploaded by %s, %s views%s %s" % (
                video_title, video_duration, video_uploader, "{:,}".format(
                int(video_views)), video_opinions, URL_YOUTUBESHORT % video_id)

    def get_playlist_page(self, playlist_id, part):
         return utils.http.request(URL_YOUTUBEPLAYLIST, get_params={
            "part": part, "id": playlist_id,
            "key": self.bot.config["google-api-key"]}, json=True)
    def playlist_details(self, playlist_id):
        snippet = self.get_playlist_page(playlist_id, "snippet")
        if snippet.data["items"]:
            snippet = snippet.data["items"][0]["snippet"]

            content = self.get_playlist_page(playlist_id, "contentDetails")
            count = content.data["items"][0]["contentDetails"]["itemCount"]

            return "%s - %s (%d %s) %s" % (snippet["channelTitle"],
                snippet["title"], count, "video" if count == 1 else "videos",
                URL_PLAYLIST % playlist_id)

    def _from_url(self, url):
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.hostname == "youtu.be" and parsed.path:
            return self.video_details(parsed.path[1:])
        elif parsed.path == "/watch" and "v" in query:
            return self.video_details(query["v"][0])
        elif parsed.path == "/playlist" and "list" in query:
            return self.playlist_details(query["list"][0])

    def _search_youtube(self, query):
        video_id = ""

        search_page = utils.http.request(URL_YOUTUBESEARCH,
            get_params={"q": query, "part": "snippet",
            "maxResults": "1", "type": "video",
            "key": self.bot.config["google-api-key"]},
             json=True)

        if search_page:
            if search_page.data["pageInfo"]["totalResults"] > 0:
                video_id = search_page.data["items"][0]["id"]["videoId"]
                return "https://youtu.be/%s" % video_id

    @utils.hook("received.command.yt", alias_of="youtube")
    @utils.hook("received.command.youtube")
    def yt(self, event):
        """
        :help: Find a video on youtube
        :usage: [query/URL]
        """
        url = None
        search = None
        if event["args"]:
            search = event["args"]
            url_match = re.match(REGEX_YOUTUBE, event["args"])
            if url_match:
                url = event["args"]
            else:
                search = event["args"]
        else:
            url = event["target"].buffer.find(REGEX_YOUTUBE)
            url = url.match if url else None

        if not url:
            safe_setting = event["target"].get_setting("youtube-safesearch", True)
            safe = "moderate" if safe_setting else "none"
            search_page = utils.http.request(URL_YOUTUBESEARCH,
                get_params={"q": search, "part": "snippet", "maxResults": "1",
                "type": "video", "key": self.bot.config["google-api-key"],
                "safeSearch": safe}, json=True)
            if search_page:
                if search_page.data["pageInfo"]["totalResults"] > 0:
                    url = URL_VIDEO % search_page.data[
                        "items"][0]["id"]["videoId"]
                else:
                    raise utils.EventError("No videos found")
            else:
                raise utils.EventsResultsError()

        if url:
            out = self._from_url(url)
            if not out == None:
                event["stdout"].write(out)
            else:
                raise utils.EventsResultsError()
        else:
            event["stderr"].write("No search phrase provided")

    @utils.hook("command.regex")
    @utils.kwarg("priority", EventManager.PRIORITY_LOW)
    @utils.kwarg("ignore_action", False)
    @utils.kwarg("command", "youtube")
    @utils.kwarg("pattern", REGEX_YOUTUBE)
    def channel_message(self, event):
        if event["target"].get_setting("auto-youtube", False):
            out = self._from_url(event["match"].group(0))
            if not out == None:
                event.eat()
                event["stdout"].write(out)
