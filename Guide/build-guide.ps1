[CmdletBinding()]
param(
    [string]$SourcePath = (Join-Path $PSScriptRoot 'DW4_UnifiedGuide.md'),
    [string]$OutputDirectory = $PSScriptRoot,
    [string]$PandocPath = '',
    [string]$LaTeXPath = '',
    [switch]$TexOnly
)

$ErrorActionPreference = 'Stop'

function Invoke-BoundedTool {
    param(
        [string]$Executable,
        [string[]]$ChildArguments,
        [string]$WorkingDirectory,
        [int]$TimeoutSeconds = 300
    )

    $stdoutPath = Join-Path $WorkingDirectory 'tool.stdout.log'
    $stderrPath = Join-Path $WorkingDirectory 'tool.stderr.log'
    $quotedArguments = foreach ($argument in $ChildArguments) {
        $escaped = [regex]::Replace($argument, '(\\*)"', '$1$1\"')
        $escaped = [regex]::Replace($escaped, '\\+$', '$0$0')
        '"' + $escaped + '"'
    }

    $process = Start-Process -FilePath $Executable -ArgumentList $quotedArguments `
        -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $null = $process.Handle
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "$Executable exceeded its $TimeoutSeconds-second limit."
    }
    $process.WaitForExit()

    $result = [pscustomobject]@{
        ExitCode = $process.ExitCode
        StandardOutput = [System.IO.File]::ReadAllText($stdoutPath)
        StandardError = [System.IO.File]::ReadAllText($stderrPath)
    }
    $process.Dispose()
    if ($result.ExitCode -ne 0) {
        $details = ($result.StandardOutput + "`n" + $result.StandardError) -split '\r?\n'
        throw ("$Executable failed with exit code $($result.ExitCode).`n" +
            (($details | Select-Object -Last 45) -join "`n"))
    }
    $result
}

$SourcePath = (Resolve-Path -LiteralPath $SourcePath).Path
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
$stem = [System.IO.Path]::GetFileNameWithoutExtension($SourcePath)
$workDirectory = Join-Path ([System.IO.Path]::GetTempPath()) `
    ('dw4-guide-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $workDirectory

try {
    if (-not $PandocPath) {
        $installedPandoc = Get-Command pandoc -ErrorAction SilentlyContinue
        if ($installedPandoc) {
            $PandocPath = $installedPandoc.Source
        }
        else {
            Write-Host 'Downloading official portable Pandoc into the temporary build directory...'
            $release = Invoke-RestMethod `
                -Uri 'https://api.github.com/repos/jgm/pandoc/releases/latest' -TimeoutSec 60
            $asset = $release.assets | Where-Object {
                $_.name -match '^pandoc-.+-windows-x86_64\.zip$'
            } | Select-Object -First 1
            if ($null -eq $asset) {
                throw 'The official Pandoc release has no Windows portable archive.'
            }
            $archive = Join-Path $workDirectory $asset.name
            Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url `
                -OutFile $archive -TimeoutSec 120
            Expand-Archive -LiteralPath $archive -DestinationPath $workDirectory
            $PandocPath = (Get-ChildItem -LiteralPath $workDirectory -Filter pandoc.exe `
                -Recurse | Select-Object -First 1).FullName
        }
    }
    if (-not (Test-Path -LiteralPath $PandocPath -PathType Leaf)) {
        throw 'Pandoc was not found. Supply its executable with -PandocPath.'
    }

    if (-not $TexOnly -and -not $LaTeXPath) {
        $installedLaTeX = Get-Command xelatex -ErrorAction SilentlyContinue
        if ($installedLaTeX) {
            $LaTeXPath = $installedLaTeX.Source
        }
        else {
            throw 'XeLaTeX was not found. Install MiKTeX/TeX Live, or use -TexOnly.'
        }
    }
    if (-not $TexOnly -and -not (Test-Path -LiteralPath $LaTeXPath -PathType Leaf)) {
        throw 'The -LaTeXPath executable does not exist.'
    }

    $filter = @'
local function rows_of(tbl)
  local rows = {}
  for _, row in ipairs(tbl.head.rows) do rows[#rows + 1] = row end
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.head) do rows[#rows + 1] = row end
    for _, row in ipairs(body.body) do rows[#rows + 1] = row end
  end
  for _, row in ipairs(tbl.foot.rows) do rows[#rows + 1] = row end
  return rows
end

local function fingerprint(blocks)
  local words = {}
  local counts = { headings = 0, tables = 0, cells = 0, quotes = 0 }
  pandoc.Pandoc(blocks):walk({
    Str = function(value) words[#words + 1] = value.text end,
    Code = function(value) words[#words + 1] = value.text end,
    Math = function(value) words[#words + 1] = value.text end,
    Header = function() counts.headings = counts.headings + 1 end,
    BlockQuote = function() counts.quotes = counts.quotes + 1 end,
    Table = function(tbl)
      counts.tables = counts.tables + 1
      for _, row in ipairs(rows_of(tbl)) do
        counts.cells = counts.cells + #row.cells
      end
    end
  })
  return table.concat(words, '\0'), counts
end

local numeric_weights = {
  ['#'] = 0.45, id = 0.8, points = 0.6, cost = 0.85,
  ['coin cost'] = 0.85, power = 0.75, hp = 0.65, mp = 0.65,
  exp = 0.8, gold = 0.85, level = 0.65, achievements = 0.9
}

local function format_table(tbl)
  local columns = #tbl.colspecs
  local labels, lengths, weights = {}, {}, {}
  local rows = rows_of(tbl)
  local numeric_count = 0
  for column = 1, columns do
    labels[column] = ''
    lengths[column] = 0
    if tbl.head.rows[1] and tbl.head.rows[1].cells[column] then
      labels[column] = pandoc.utils.stringify(
        tbl.head.rows[1].cells[column].contents):lower()
    end
    for _, row in ipairs(rows) do
      if row.cells[column] then
        lengths[column] = lengths[column] +
          #pandoc.utils.stringify(row.cells[column].contents)
      end
    end
    if numeric_weights[labels[column]] then
      numeric_count = numeric_count + 1
      weights[column] = numeric_weights[labels[column]]
    else
      weights[column] = math.max(1.2, math.min(4.5,
        0.7 + math.sqrt(lengths[column] / math.max(1, #rows)) / 3))
    end
  end

  local total = 0
  for _, weight in ipairs(weights) do total = total + weight end
  for column = 1, columns do
    tbl.colspecs[column] = { tbl.colspecs[column][1], weights[column] / total }
  end

  local function style_header(block)
    block.content:insert(1, pandoc.RawInline('latex', [[\color{GuideGreen}\bfseries ]]))
    return block
  end
  for _, row in ipairs(tbl.head.rows) do
    for _, cell in ipairs(row.cells) do
      cell.contents = cell.contents:walk({ Plain = style_header, Para = style_header })
    end
  end

  local landscape = columns >= 5 and numeric_count <= 1
  for _, label in ipairs(labels) do
    if label == 'primary section' then landscape = true end
  end
  local before = [[\begin{guidetable}]]
  local after = [[\end{guidetable}]]
  if landscape then
    before = [[\begin{landscape}]] .. '\n' .. before
    after = after .. '\n' .. [[\end{landscape}]]
  end
  return { pandoc.RawBlock('latex', before), tbl, pandoc.RawBlock('latex', after) }
end

function Pandoc(document)
  assert(document.blocks[1].t == 'Header' and document.blocks[1].level == 1,
    'Expected the guide to begin with its title.')
  document.meta.title = pandoc.MetaInlines(document.blocks[1].content)
  document.blocks:remove(1)

  local targets = { ['table-of-contents'] = true }
  for _, block in ipairs(document.blocks) do
    if block.t == 'Header' then
      if block.identifier == 'table-of-contents' then
        block.identifier = 'route-overview'
        block.content = pandoc.Inlines({ pandoc.Str('Route'), pandoc.Space(),
          pandoc.Str('Overview') })
      end
      targets[block.identifier] = true
    end
  end

  local expected, original = fingerprint(document.blocks)
  document = document:walk({
    Header = function(header)
      header.level = header.level - 1
      if header.identifier == 'introduction' then
        return { pandoc.RawBlock('latex', [[\clearpage\pagenumbering{arabic}]]), header }
      end
      return header
    end,
    Link = function(link)
      if link.target:sub(1, 1) == '#' then
        assert(targets[link.target:sub(2)], 'Missing internal link target: ' .. link.target)
      end
    end,
    Table = format_table,
    BlockQuote = function(quote)
      local text = pandoc.utils.stringify(quote.content)
      local environment = 'guidenote'
      if text:match('^Achievement Alert:') then environment = 'achievementalert' end
      if text:match('^Achievement Setup:') then environment = 'achievementsetup' end
      local blocks = { pandoc.RawBlock('latex', [[\begin{]] .. environment .. '}') }
      for _, block in ipairs(quote.content) do blocks[#blocks + 1] = block end
      blocks[#blocks + 1] = pandoc.RawBlock('latex', [[\end{]] .. environment .. '}')
      return blocks
    end
  })

  local laid_out = pandoc.Blocks({})
  local section_start, chapter_start = 1, 1
  local chapter_has_sections = false
  local chapter_title = ''
  local landscape_start = [[\begin{landscape}]] .. '\n' .. [[\begin{guidetable}]]
  for _, block in ipairs(document.blocks) do
    if block.t == 'Header' then
      if block.level == 1 then
        chapter_title = pandoc.write(pandoc.Pandoc({ pandoc.Plain(block.content) }),
          'latex'):gsub('%s+$', '')
        chapter_start = #laid_out + 1
        chapter_has_sections = false
        section_start = chapter_start
      elseif not chapter_has_sections then
        section_start = chapter_start
        chapter_has_sections = true
      else
        section_start = #laid_out + 1
      end
    end
    if block.t == 'RawBlock' and block.format == 'latex' and block.text == landscape_start then
      laid_out:insert(section_start, pandoc.RawBlock('latex', [[\begin{landscape}]]))
      block.text = [[\begin{guidetable}]]
    end
    if block.t == 'RawBlock' and block.text:find([[\end{landscape}]], 1, true) then
      block.text = block.text .. '\n' .. [[\chaptermark{]] .. chapter_title .. '}'
    end
    laid_out:insert(block)
    if block.t == 'RawBlock' and block.text:find([[\end{guidetable}]], 1, true) then
      section_start = #laid_out + 1
    end
  end
  document.blocks = laid_out

  local actual, converted = fingerprint(document.blocks)
  assert(actual == expected, 'Conversion changed the guide text or its reading order.')
  assert(converted.tables == original.tables and converted.cells == original.cells,
    'Conversion lost a table or table cell.')
  assert(converted.headings == original.headings, 'Conversion lost a heading.')
  io.stderr:write(string.format(
    'Content verified: %d headings, %d tables, %d table cells, %d callouts; all body text preserved.\n',
    original.headings, original.tables, original.cells, original.quotes))
  return document
end
'@

    $preamble = @'
\usepackage{fontspec}
\IfFontExistsTF{Palatino Linotype}{\setmainfont{Palatino Linotype}}{\setmainfont{TeX Gyre Pagella}}
\IfFontExistsTF{Trebuchet MS}{\setsansfont{Trebuchet MS}}{\setsansfont{TeX Gyre Heros}}
\IfFontExistsTF{Consolas}{\setmonofont{Consolas}[Scale=0.88]}{\setmonofont{Latin Modern Mono}[Scale=0.88]}
\usepackage{microtype}
\usepackage{pdflscape}
\usepackage[breakable,skins]{tcolorbox}
\usepackage[automark]{scrlayer-scrpage}
\definecolor{GuideGreen}{HTML}{244D3E}
\definecolor{GuideGold}{HTML}{95722D}
\definecolor{GuideRed}{HTML}{803E42}
\definecolor{GuideBlue}{HTML}{2C5870}
\KOMAoptions{parskip=half,headings=small,headsepline=0.4pt}
\setkomafont{disposition}{\sffamily\bfseries\color{GuideGreen}}
\setkomafont{chapter}{\sffamily\bfseries\color{GuideGreen}\fontsize{24}{28}\selectfont}
\setkomafont{section}{\sffamily\bfseries\color{GuideGreen}\large}
\setkomafont{subsection}{\sffamily\bfseries\color{GuideRed}\normalsize}
\RedeclareSectionCommand[beforeskip=10pt,afterskip=18pt]{chapter}
\RedeclareSectionCommand[beforeskip=16pt,afterskip=7pt]{section}
\RedeclareSectionCommand[beforeskip=12pt,afterskip=5pt]{subsection}
\makeatletter
\renewcommand{\@pnumwidth}{2.5em}
\renewcommand{\@tocrmarg}{3.5em}
\makeatother
\clearpairofpagestyles
\automark[chapter]{chapter}
\ihead{\parbox[b]{0.83\textwidth}{\raggedright\sffamily\footnotesize\headmark}}
\ohead{\sffamily\scriptsize DW IV}
\ifoot{\sffamily\scriptsize Dragon Warrior IV}
\ofoot[\pagemark]{\pagemark}
\setkomafont{pageheadfoot}{\normalfont\sffamily\footnotesize}
\pagestyle{scrheadings}
\raggedbottom
\emergencystretch=2em
\setlength{\LTleft}{0pt}
\setlength{\LTright}{0pt}
\newenvironment{guidetable}{%
  \small\setstretch{1.0}%
  \setlength{\tabcolsep}{4pt}%
  \setlength{\LTpre}{8pt}\setlength{\LTpost}{10pt}%
  \renewcommand{\arraystretch}{1.16}%
}{ }
\tcbset{guidebox/.style={enhanced,breakable,boxrule=0.4pt,leftrule=2pt,
  arc=1pt,left=8pt,right=8pt,top=6pt,bottom=6pt,
  before skip=10pt,after skip=10pt}}
\newtcolorbox{achievementalert}{guidebox,colback=GuideGreen!4!white,colframe=GuideGreen}
\newtcolorbox{achievementsetup}{guidebox,colback=GuideGold!6!white,colframe=GuideGold}
\newtcolorbox{guidenote}{guidebox,colback=GuideBlue!4!white,colframe=GuideBlue}
\AtBeginDocument{\hypersetup{colorlinks=true,linkcolor=GuideGreen,urlcolor=GuideBlue,
  citecolor=GuideGreen,bookmarksopen=true,bookmarksopenlevel=0,
  bookmarksdepth=2,pdfpagelabels=true}}
\let\GuideOriginalContents\tableofcontents
\renewcommand{\tableofcontents}{%
  \clearpage\phantomsection\label{table-of-contents}%
  \GuideOriginalContents\clearpage
}
\renewcommand{\maketitle}{%
  \begin{titlepage}
  \thispagestyle{empty}\sffamily
  \setlength{\parfillskip}{0pt plus 1fil}
  \noindent{\small\textcolor{GuideGreen}{NINTENDO ENTERTAINMENT SYSTEM}}\par
  \vspace*{0.95in}
  \noindent\textcolor{GuideGreen}{\rule{\textwidth}{1.6pt}}\par
  \vspace{0.25in}
  {\fontsize{35}{41}\selectfont\bfseries\color{GuideGreen}Dragon Warrior IV\par}
  \vspace{0.15in}
  {\fontsize{23}{29}\selectfont Unified Walkthrough\par}
  \vspace{0.45in}
  {\large Story routes, achievement planning,\par and reference tables\par}
  \vspace{0.35in}
  {\normalsize Chapters 1--5\quad\textbullet\quad 43 achievements\quad\textbullet\quad 360 points\par}
  \vfill
  \noindent\textcolor{GuideGold}{\rule{\textwidth}{0.8pt}}\par
  \vspace{0.12in}
  {\footnotesize Dragon Warrior IV Unified Walkthrough\par}
  \end{titlepage}
  \pagenumbering{roman}
}
'@

    $encoding = New-Object System.Text.UTF8Encoding($false)
    $filterPath = Join-Path $workDirectory 'guide-format.lua'
    $preamblePath = Join-Path $workDirectory 'guide-preamble.tex'
    [System.IO.File]::WriteAllText($filterPath, $filter, $encoding)
    [System.IO.File]::WriteAllText($preamblePath, $preamble, $encoding)
    $texPath = Join-Path $workDirectory ($stem + '.tex')
    $result = Invoke-BoundedTool -Executable $PandocPath -WorkingDirectory $workDirectory `
        -TimeoutSeconds 120 -ChildArguments @(
            $SourcePath, '--from=markdown', '--to=latex', '--standalone', '--toc',
          '--toc-depth=2', '--top-level-division=chapter', '--pdf-engine=xelatex',
            '--metadata=lang:en-US', '--metadata=date:',
            '--variable=documentclass:scrreprt', '--variable=classoption:oneside',
            '--variable=classoption:open=any', '--variable=fontsize:10pt',
            '--variable=papersize:letter', '--variable=linestretch:1.08',
            '--variable=geometry:margin=0.78in,headheight=30pt,headsep=12pt',
            "--lua-filter=$filterPath", "--include-in-header=$preamblePath", "--output=$texPath"
        )
    Write-Host $result.StandardError.Trim()

    if ((Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash -ne $sourceHash) {
        throw 'The Markdown source changed during conversion; no output will be published.'
    }
    if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $OutputDirectory
    }
    $publishedTex = Join-Path $OutputDirectory ($stem + '.tex')
    Copy-Item -LiteralPath $texPath -Destination $publishedTex

    if (-not $TexOnly) {
        for ($pass = 1; $pass -le 3; $pass++) {
            Write-Host "LaTeX pass $pass of 3..."
            $null = Invoke-BoundedTool -Executable $LaTeXPath -WorkingDirectory $workDirectory `
                -ChildArguments @(
                    '--interaction=nonstopmode', '--halt-on-error', '--file-line-error',
                    '--enable-installer', "--output-directory=$workDirectory", $texPath
                )
        }

        $log = [System.IO.File]::ReadAllText((Join-Path $workDirectory ($stem + '.log')))
        $overflow = [regex]::Matches($log, 'Overfull \\hbox \(([\d.]+)pt too wide\)') |
            Where-Object { [double]$_.Groups[1].Value -gt 1.0 }
        if ($overflow) {
          $messages = $overflow | ForEach-Object {
            $log.Substring($_.Index, [Math]::Min(240, $log.Length - $_.Index))
          }
            throw ("PDF layout check found overflowing text:`n" + ($messages -join "`n"))
        }
        if ($log -match 'There were undefined references|undefined on input line|Rerun to get cross-references right|Table widths have changed') {
            throw 'The PDF still has unresolved references or unstable table widths after three passes.'
        }
        $pdfPath = Join-Path $workDirectory ($stem + '.pdf')
        if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
            throw 'LaTeX did not produce a PDF.'
        }
        $publishedPdf = Join-Path $OutputDirectory ($stem + '.pdf')
        Copy-Item -LiteralPath $pdfPath -Destination $publishedPdf
        $pageMatch = [regex]::Match($log, 'Output written on [\s\S]+?\((\d+) pages')
        Write-Host "PDF verified: $($pageMatch.Groups[1].Value) pages; no overflowing text or unresolved references."
        Write-Host "PDF: $publishedPdf"
    }
    Write-Host "LaTeX: $publishedTex"
    Write-Host 'Markdown source unchanged (SHA-256 verified).'
}
finally {
    Remove-Item -LiteralPath $workDirectory -Recurse -Force
}