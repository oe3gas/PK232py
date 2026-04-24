Get-ChildItem src/pk232py -Recurse -Filter "*.py" | 
  ForEach-Object { 
    "# === $($_.FullName) ===`n" + (Get-Content $_.FullName -Raw) + "`n`n"
  } | Out-File pk232py_sources.txt -Encoding UTF8