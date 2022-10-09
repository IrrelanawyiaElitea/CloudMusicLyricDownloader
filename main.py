import sys

import mutagen
import pathlib
import requests
import json
import re
import easygui
from multiprocessing.dummy import Pool,Lock

title = "网易云歌词下载助手"


def distance(word1: str, word2: str) -> int:
    n = len(word1)
    m = len(word2)

    if n * m == 0:
        return n + m

    D = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            left = D[i - 1][j] + 1
            down = D[i][j - 1] + 1
            left_down = D[i - 1][j - 1]
            if word1[i - 1] != word2[j - 1]:
                left_down += 1
            D[i][j] = min(left, down, left_down)

    return D[n][m]


class TagLoader():
    MusicType = {'.mp3', '.flac'}

    @staticmethod
    def getMusicPaths(folderPath: pathlib.Path):
        return [i for i in folderPath.iterdir() if i.suffix in TagLoader.MusicType]

    @staticmethod
    def lyricPath(musicPath):
        return musicPath.parent / (musicPath.stem + '.lrc')

    @staticmethod
    def getTags(musicPath):
        mtag = dict(mutagen.File(musicPath).tags)
        tag = {}
        if 'title' in mtag.keys():
            tag['title'] = mtag['title'][0]
        elif 'TIT2' in mtag.keys():
            tag['title'] = mtag['TIT2'].text[0]
        else:
            print(f"{musicPath.name}无匹配tag")
            tag['title'] = musicPath.stem

        if 'album' in mtag.keys():
            tag['album'] = mtag['album'][0]
        elif 'TALB' in mtag.keys():
            tag['album'] = mtag['TALB'].text[0]
        return tag


class LyricDownloader():
    SearchAPI = "http://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s={{{}}}&type=1&offset=0&total=true&limit=100"
    LyricAPI = "http://music.163.com/api/song/lyric?id={}&lv=1&kv=1&tv=-1"
    LyricMatcher = re.compile(r"^(\[\d+:\d+.\d+\])(.*)$")

    @staticmethod
    def searchMusic(tag):
        "根据音乐tag搜索100首歌，计算音乐名和专辑名的编辑距离并排序，选最匹配的，返回音乐id"
        songs = json.loads(requests.get(LyricDownloader.SearchAPI.format(tag['title'])).text)['result']['songs']
        distances = []
        for s in songs:
            id = s['id']
            titleD = distance(s['name'], tag['title'])
            if 'album' in tag:
                albumD = distance(s['album']['name'], tag['album'])
            else:
                albumD = 0
            distances.append((id, titleD, albumD, s['name'], s['album']['name']))
        distances.sort(key=lambda x: (x[1], x[2]))
        return distances[0][0]

    @staticmethod
    def getLyric(id):
        "根据id获取歌词，然后清洗成lrc格式"
        lyric = json.loads(requests.get(LyricDownloader.LyricAPI.format(id)).text)
        if 'lrc' in lyric.keys():
            lrc = [LyricDownloader.LyricMatcher.match(i) for i in lyric['lrc']['lyric'].split('\n')]
            lrc = [i.groups() for i in lrc if i is not None]
        else:
            lrc = []
        if 'tlyric' in lyric.keys():
            tlrc = [LyricDownloader.LyricMatcher.match(i) for i in lyric['tlyric']['lyric'].split('\n')]
            tlrc = dict([i.groups() for i in tlrc if i is not None])
        else:
            tlrc = []

        mlrc = []
        for i in lrc:
            ts = i[0].split('.')[0] + '.' + i[0].split('.')[1][:2] + ']'
            mlrc.append(f"{ts}{i[1]}  {tlrc.get(i[0], '')}")
        mlrc = '\n'.join(mlrc)
        return mlrc


class Main():
    def __init__(self):
        self.overwrite = False
        self.askIfOverwrite = True
        self.config = json.load(open('./config.json','r',encoding='utf8'))
        self.lock = Lock()
        if self.config['multiThread']:
            self.pool = Pool(self.config['threadNum'])
            self.work = self.multiwork
        else:
            self.work = self.singlework

    def init(self):
        self.path = pathlib.Path(easygui.diropenbox("选择音乐目录"))
        self.musicList = TagLoader.getMusicPaths(self.path)
        self.succ = 0
        self.fail = 0
        self.jump = 0

    def ifOverwrite(self):
        if not self.askIfOverwrite:
            return self.overwrite
        else:
            self.lock.acquire()
            if self.askIfOverwrite: #防止选了总是或者从不还是跳很多框
                answer = easygui.buttonbox("发现歌词已存在。是否覆盖？", title, ["是", "否", "总是", "从不"])
            else:
                self.lock.release()
                return self.overwrite
            self.lock.release()
            if answer == "是":
                return True
            elif answer == "否":
                return False
            elif answer == "总是":
                self.askIfOverwrite = False
                self.overwrite = True
                return True
            elif answer == "从不":
                self.askIfOverwrite = False
                self.overwrite = False
                return False
        raise Exception("这代码不应该运行到这里的！！！！！！！！！！！！！！！！")

    def download(self, musicPath):
        try:
            lrcPath = TagLoader.lyricPath(musicPath)
            if lrcPath.exists():
                overwrite = self.ifOverwrite()
                if not overwrite:
                    self.jump += 1
                    return
            tag = TagLoader.getTags(musicPath)
            id = LyricDownloader.searchMusic(tag)
            lyric = LyricDownloader.getLyric(id)
            with open(TagLoader.lyricPath(musicPath), 'w', encoding='utf8') as f:
                f.write(lyric)
            self.succ += 1
            if len(lyric) > 0:
                print(f"下载成功  {musicPath.stem}")
            else:
                print(f"下载成功  未发现歌词  {musicPath.stem} ")
        except:
            self.fail += 1
            print(f"下载失败  {musicPath.stem}")

    def singlework(self):
        self.init()
        for musicPath in self.musicList:
            self.download(musicPath)
        cont = easygui.ynbox(f"下载完成！\n成功：{self.succ}\n失败：{self.fail}\n跳过：{self.jump}\n是否继续下载？", title)
        return cont

    def multiwork(self):
        self.init()
        self.pool.map(self.download, self.musicList)
        cont = easygui.ynbox(f"下载完成！\n成功：{self.succ}\n失败：{self.fail}\n跳过：{self.jump}\n是否继续下载？", title)
        return cont

    def main(self):
        cont = True
        while cont:
            cont = self.work()


if __name__ == "__main__":
    main = Main()
    main.main()

# nuitka --standalone --enable-plugin=tk-inter main.py
