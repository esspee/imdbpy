"""
parser.mobile package (imdb package).

This package provides the IMDbMobileAccessSystem class used to access
IMDb's data for mobile systems.
the imdb.IMDb function will return an instance of this class when
called with the 'accessSystem' argument set to "mobile".

Copyright 2005 Davide Alberani <da@erlug.linux.it>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

import re, urllib
from htmlentitydefs import entitydefs
from sgmllib import entityref, charref

from imdb.Movie import Movie
from imdb.Person import Person
from imdb.utils import analyze_title, analyze_name, \
                        canonicalTitle, canonicalName
from imdb._exceptions import IMDbDataAccessError
from imdb.parser.http import IMDbHTTPAccessSystem, imdbURL_search, \
                                imdbURL_movie, imdbURL_person

# XXX NOTE: the first version of this module was heavily based on
#           regular expressions.  This new version replace regexps with
#           find() strings methods; despite being less flexible, it
#           seems to be at least as fast and, hopefully, much more
#           lightweight.

# To strip spaces.
re_spaces = re.compile(r'\s+')
# Strip html.
re_unhtml = re.compile(r'<.+?>')
# imdb person or movie ids.
re_imdbID = re.compile(r'(?<=nm|tt)([0-9]{7})\b')

# Here to handle non-breaking spaces.
entitydefs['nbsp'] = ' '


def _replRef(match):
    """Replace the matched html/sgml entity and reference."""
    ret = match.group()[1:-1]
    ret = entitydefs.get(ret, ret)
    if ret[0] == '#':
        try:
            ret = chr(int(ret[1:]))
            if ret == '\xa0': ret = ' '
        except (ValueError, TypeError, OverflowError):
            try:
                ret = unichr(int(ret[1:])).encode('utf-8')
            except (ValueError, TypeError, OverflowError):
                pass
            pass
    return ret


def _subRefs(s):
    """Return the given html string with entity and char references
    replaced."""
    s = entityref.sub(_replRef, s)
    s = charref.sub(_replRef, s)
    return s


def _unHtml(s):
    """Return a string without tags."""
    return re_spaces.sub(' ', re_unhtml.sub('', s)).strip()


_ltypes = (type([]), type(()))

def _getTagWith(s, cont):
    """Return the html tags in the 's' string containing the 'cont'
    string."""
    lres = []
    bi = s.find(cont)
    if bi != -1:
        btag = s[:bi].rfind('<')
        if btag != -1:
            etag = s[bi+1:].find('>')
            if etag != -1:
                lres.append(s[btag:bi+2+etag])
                lres += _getTagWith(s[btag+1+etag:], cont)
    return lres


def _findBetween(s, begins, ends, beginindx=0):
    """Return the list of string from the s string which included
    between the begins and ends strings."""
    lres = []
    #if endindx is None: endindx = len(s)
    bi = s.find(begins, beginindx)
    if bi != -1:
        lbegins = len(begins)
        if type(ends) in _ltypes:
            eset = [s.find(end, bi+lbegins) for end in ends]
            eset[:] = [x for x in eset if x != -1]
            if not eset: ei = -1
            else: ei = min(eset)
        else:
            ei = s.find(ends, bi+lbegins)
        if ei != -1:
            match = s[bi+lbegins:ei]
            lres.append(match)
            lres += _findBetween(s, begins, ends, ei)
            #if maxRes > 0 and len(lres) >= maxRes: return lres
    return lres


class IMDbMobileAccessSystem(IMDbHTTPAccessSystem):
    """The class used to access IMDb's data through the web for
    mobile terminals."""

    accessSystem = 'mobile'

    def __init__(self, isThin=1, *arguments, **keywords):
        IMDbHTTPAccessSystem.__init__(self, isThin, *arguments, **keywords)
        self.accessSystem = 'mobile'

    def _mretrieve(self, url):
        """Retrieve an html page and normalize it."""
        cont = IMDbHTTPAccessSystem._retrieve(self, url)
        cont = re_spaces.sub(' ', cont)
        return _subRefs(cont)

    def _getPersons(self, s, sep='<br>', hasCr=0):
        """Return a list of Person objects, from the string s; items
        are separated by the sep string; if hasCr is set, the
        currentRole of a person is searched."""
        names = s.split(sep)
        pl = []
        for name in names:
            notes = ''
            currentRole = ''
            fpi = name.find(' (')
            if fpi != -1:
                fpe = name.rfind(')')
                if fpe > fpi:
                    notes = _unHtml(name[fpi:fpe+1])
                    name = name[:fpi] + name[fpe+1:]
                    name = name.replace('&', '')
            if hasCr:
                name = name.split(' .... ')
                if len(name) > 1:
                    currentRole = _unHtml(name[1])
                name = name[0]
            pid = re_imdbID.findall(name)
            name = _unHtml(name)
            if not (pid and name): continue
            pl.append(Person(personID=pid[0], name=canonicalName(name),
                            currentRole=currentRole, notes=notes,
                            accessSystem=self.accessSystem,
                            modFunct=self._defModFunct))
        return pl

    def _search_movie(self, title, results):
        params = urllib.urlencode({'tt': 'on', 'mx': str(results), 'q': title})
        cont = self._mretrieve(imdbURL_search % params)
        title = _findBetween(cont, '<title>', '</title>')
        res = []
        if not title: return res
        tl = title[0].lower()
        if not tl.startswith('imdb title'):
            # XXX: a direct hit!
            title = _unHtml(title[0])
            midtag = _getTagWith(cont, 'name="arg"')
            mid = None
            if midtag: mid = _findBetween(midtag[0], 'value="', '"')
            if not (mid and title): return res
            res[:] = [(mid[0], analyze_title(title, canonical=1))]
        else:
            lis = _findBetween(cont, '<li>', ['</li>', '<br>'])
            for li in lis:
                imdbid = re_imdbID.findall(li)
                mtitle = _unHtml(li)
                if not (imdbid and mtitle): continue
                res.append((imdbid[0], analyze_title(mtitle, canonical=1)))
        return res

    def get_movie_main(self, movieID):
        cont = self._mretrieve(imdbURL_movie % movieID + 'maindetails')
        d = {}
        title = _findBetween(cont, '<title>', '</title>')
        if not title:
            raise IMDbDataAccessError, 'unable to get movieID "%s"' % movieID
        title = _unHtml(title[0])
        d = analyze_title(title, canonical=1)
        direct = _findBetween(cont, 'Directed by</b><br>', '<br> <br>')
        if direct:
            dirs = self._getPersons(direct[0])
            if dirs: d['director'] = dirs
        writers = _findBetween(cont, 'Writing credits</b>', '<br> <br>')
        if writers:
            ws = self._getPersons(writers[0])
            if ws: d['writer'] = ws
        cvurl = _getTagWith(cont, 'alt="cover"')
        if cvurl:
            cvurl = _findBetween(cvurl[0], 'src="', '"')
            if cvurl: d['cover url'] = cvurl[0]
        genres = _findBetween(cont, 'href="/Sections/Genres/', '/')
        if genres: d['genres'] = genres
        ur = _findBetween(cont, 'User Rating:</b>', ' votes)')
        if ur:
            rat = _findBetween(ur[0], '<b>', '</b>')
            if rat:
                teni = rat[0].find('/10')
                if teni != -1:
                    rat = rat[0][:teni]
                    try:
                        rat = float(rat.strip())
                        d['rating'] = rat
                    except ValueError:
                        pass
            vi = ur[0].rfind('(')
            if vi != -1 and ur[0][vi:].find('await') == -1:
                try:
                    votes = int(ur[0][vi+1:].replace(',', '').strip())
                    d['votes'] = votes
                except ValueError:
                    pass
        top250 = _findBetween(cont, 'href="/top_250_films"', '</a>')
        if top250:
            fn = top250[0].rfind('#')
            if fn != -1:
                try:
                    td = int(top250[0][fn+1:])
                    d['top 250 rank'] = td
                except ValueError:
                    pass
        castdata = _findBetween(cont, 'Cast overview', '</table>')
        if not castdata:
            castdata = _findBetween(cont, 'Credited cast', '</table>')
        if castdata:
            fl = castdata[0].find('href=')
            if fl != -1: castdata[0] = '< a' + castdata[0][fl:]
            cast = self._getPersons(castdata[0], sep='</tr><tr>', hasCr=1)
            if cast: d['cast'] = cast
        # FIXME: doesn't catch "complete title", which is not
        #        included in <i> tags.
        #        See "Gehr Nany Fgbevrf 11", movieID: 0282910
        akas = _findBetween(cont, '<i class="transl">', '<br')
        if akas:
            akas = [_unHtml(x).replace(' (','::(', 1).replace(' [','::[')
                    for x in akas]
            d['akas'] = akas
        mpaa = _findBetween(cont, 'MPAA</a>:', '<br>')
        if mpaa: d['mpaa'] = _unHtml(mpaa[0])
        runtimes = _findBetween(cont, 'Runtime:</b>', '<br>')
        if runtimes:
            rt = [x.strip().replace(' min', '')
                    for x in runtimes[0].split('/')]
            d['runtimes'] = rt
        country = _findBetween(cont, 'href="/Sections/Countries/', '"')
        if country: d['countries'] = country
        lang = _findBetween(cont, 'href="/Sections/Languages/', '"')
        if lang: d['languages'] = lang
        col = _findBetween(cont, '"/List?color-info=', '<br')
        if col:
            col[:] = col[0].split(' / ')
            col[:] = ['<a %s' % x for x in col if x]
            col[:] = [_unHtml(x.replace(' <i>', '::')) for x in col]
            if col: d['color'] = col
        sm = _findBetween(cont, '/List?sound-mix=', '<br>')
        if sm:
            sm[:] = sm[0].split(' / ')
            sm[:] = ['<a %s' % x for x in sm if x]
            sm[:] = [_unHtml(x.replace(' <i>', '::')) for x in sm]
            if sm: d['sound mix'] = sm
        cert = _findBetween(cont, 'Certification:</b>', '<br')
        if cert:
            cert[:] = cert[0].split(' / ')
            cert[:] = [_unHtml(x.replace(' <i>', '::')) for x in cert]
            if cert: d['certificates'] = cert
        plotoutline = _findBetween(cont, 'Plot Outline:</b>', ['<a ', '<br'])
        if plotoutline:
            plotoutline = plotoutline[0].strip()
            if plotoutline: d['plot outline'] = plotoutline
        return {'data': d}

    def get_movie_plot(self, movieID):
        cont = self._mretrieve(imdbURL_movie % movieID + 'plotsummary')
        plot = _findBetween(cont, '<p class="plotpar">', '</p>')
        plot[:] = [_unHtml(x) for x in plot]
        if plot: return {'data': {'plot': plot}}
        return {'data': {}}

    def _search_person(self, name, results):
        params = urllib.urlencode({'nm': 'on', 'mx': str(results), 'q': name})
        cont = self._mretrieve(imdbURL_search % params)
        name = _findBetween(cont, '<title>', '</title>')
        res = []
        if not name: return res
        nl = name[0].lower()
        if not nl.startswith('imdb name search'):
            # XXX: a direct hit!
            name = _unHtml(name[0])
            pidtag = _getTagWith(cont, '/board/threads/')
            pid = None
            if pidtag: pid = _findBetween(pidtag[0], '/name/nm', '/')
            if not (pid and name): return res
            res[:] = [(pid[0], analyze_name(name, canonical=1))]
        else:
            lis = _findBetween(cont, '<li>', ['<small', '</li>', '<br'])
            for li in lis:
                pid = re_imdbID.findall(li)
                pname = _unHtml(li)
                if not (pid and pname): continue
                res.append((pid[0], analyze_name(pname, canonical=1)))
        return res

    def get_person_main(self, personID):
        s = self._mretrieve(imdbURL_person % personID + 'maindetails')
        r = {}
        name = _findBetween(s, '<title>', '</title>')
        if not name:
            raise IMDbDataAccessError, 'unable to get personID "%s"' % personID
        r = analyze_name(name[0], canonical=1)
        bdate = _findBetween(s, '<div class="ch">Date of birth',
                            ('<br>', '<dt>'))
        if bdate:
            bdate = _unHtml('<a %s' % bdate[0])
            if bdate: r['birth date'] = bdate
        bnotes = _findBetween(s, 'href="/BornWhere?', '</dd>')
        if bnotes:
            bnotes = _unHtml('<a %s' % bnotes[0])
            if bnotes: r['birth notes'] = bnotes
        ddate = _findBetween(s, '<div class="ch">Date of death', '</dd>')
        if ddate:
            ddates = ddate[0].split('<br>')
            ddate = ddates[0]
            ddate = _unHtml('<a %s' % ddate)
            if ddate: r['death date'] = ddate
            dnotes = None
            if len(ddates) > 1:
                dnotes = _unHtml(ddates[1])
            if dnotes: r['death notes'] = dnotes
        akas = _findBetween(s, 'Sometimes Credited As:', '</dl>')
        if akas:
            akas[:] = [_unHtml(x) for x in akas[0].split('<br>')]
            if akas: r['akas'] = akas
        hs = _findBetween(s, 'name="headshot"', '</a>')
        if hs:
            hs[:] = _findBetween(hs[0], 'src="', '"')
            if hs: r['headshot'] = hs[0]
        workkind = _findBetween(s, 'Filmography as:</i>', '</p>')
        if not workkind: return r
        wsects = workkind[0].split(', ')
        ws = []
        for w in wsects:
            sl = _findBetween(w, 'href="#', '"')
            if not sl: continue
            sn = _findBetween(w, '">', '</a')
            if sn: sn = _unHtml(sn[0])
            if not sn: continue
            ws.append((sl[0], sn.lower()))
        for sect, sectName in ws:
            sectName = sectName.lower()
            raws = ''
            inisect = s.find('<a name="%s">' % sect)
            if inisect != -1:
                endsect = s[inisect:].find('</ol>')
                if endsect != -1: raws = s[inisect:inisect+endsect]
            if not raws: continue
            mlist = _findBetween(raws, '<li>', ('</li>', '<br>'))
            for m in mlist:
                d = {}
                d['movieID'] = m[:7]
                ti = m.find('/">')
                te = m.find('</a>')
                if ti != -1 and te > ti:
                    d['title'] = m[ti+3:te]
                    m = m[te+4:]
                else:
                    continue
                fi = m.find('<font ')
                if fi != -1:
                    fe = m.find('</font>')
                    if fe > fi:
                        fif = m[fi+6:].find('>')
                        if fif != -1:
                            d['status'] = m[fi+7+fif:fe]
                            m = m[:fi] + m[fe+7:]
                fai = m.find('<i>')
                if fai != -1:
                    fae = m[fai:].find('</i>')
                    if fae != -1:
                        m = m[:fai] + m[fai+fae+4:]
                tvi = m.find('<small>TV Series</small>')
                if tvi != -1:
                    d['title'] = '"%s"' % d['title']
                    m = m[:tvi] + m[tvi+24:]
                m = m.strip()
                for x in xrange(2):
                    if len(m) > 1 and m[0] == '(':
                        ey = m.find(')')
                        if ey != -1:
                            if m[1].isdigit() or \
                                    m[1:ey] in ('TV', 'V', 'mini', 'VG'):
                                d['title'] += ' %s' % m[:ey+1]
                                m = m[ey+1:].lstrip()
                #istvguest = 0
                #if m.find('<small>playing</small>') != -1:
                #    istvguest = 1
                m = m.replace('<small>', ' ').replace('</small>', ' ').strip()
                notes = ''
                role = ''
                ms = m.split('....')
                if len(ms) >= 1:
                    first = ms[0]
                    if first and first[0] == '(':
                        notes = first.strip()
                    ms = ms[1:]
                if ms: role = ' '.join(ms).strip()
                movie = Movie(title=d['title'], accessSystem=self.accessSystem,
                                movieID=d['movieID'],
                                modFunct=self._defModFunct)
                if d.has_key('status'): movie['status'] = d['status']
                movie.currentRole = role
                movie.notes = notes
                if not r.has_key(sectName): r[sectName] = []
                r[sectName].append(movie)
        return {'data': r, 'info sets': ('main', 'filmography')}

    def get_person_biography(self, personID):
        cont = self._mretrieve(imdbURL_person % personID + 'bio')
        d = {}
        spouses = _findBetween(cont, 'Spouse</dt>', ('</table>', '</dd>'))
        if spouses:
            sl = []
            for spouse in spouses[0].split('</tr>'):
                if spouse.count('</td>') > 1:
                    spouse = spouse.replace('</td>', '::</td>', 1)
                spouse = _unHtml(spouse)
                spouse = spouse.replace(':: ', '::').strip()
                if spouse: sl.append(spouse)
            if sl: d['spouse'] = sl
        misc_sects = _findBetween(cont, '<dt class="ch">', ('<hr', '</dd>'))
        misc_sects[:] = [x.split('</dt>') for x in misc_sects]
        misc_sects[:] = [x for x in misc_sects if len(x) == 2]
        for sect, data in misc_sects:
            sect = sect.lower().replace(':', '').strip()
            if sect == 'salary': sect = 'salary history'
            if sect in ('imdb mini-biography by', 'spouse'):
                continue
            data = data.replace('</p><p class="biopar">', '::')
            data = data.replace('</td>\n<td valign="top">', '@@@@')
            data = data.replace('</td>\n</tr>', '::')
            data = _unHtml(data)
            data = [x.strip() for x in data.split('::')]
            data[:] = [x.replace('@@@@', '::') for x in data if x]
            if sect in ('birth name', 'height') and data: data = data[0]
            d[sect] = data
        return {'data': d}

