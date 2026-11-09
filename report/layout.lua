-- Give pipe tables real wrapping widths in the printable report.
-- Markdown and its measured values remain unchanged.
function Table(tbl)
  local count = #tbl.colspecs
  local heading = pandoc.utils.stringify(tbl.head.rows[1].cells[1].contents)
  local widths = {}
  if count == 2 then
    if heading:match("Reference") then
      widths = {0.57, 0.43}
    elseif heading:match("Code") then
      widths = {0.10, 0.90}
    else
      widths = {0.26, 0.74}
    end
  elseif count == 3 then
    widths = {0.15, 0.32, 0.53}
  elseif count == 9 then
    widths = {0.145, 0.09, 0.18, 0.06, 0.11, 0.11, 0.095, 0.095, 0.115}
  else
    for i = 1, count do widths[i] = 1 / count end
  end
  for i = 1, count do tbl.colspecs[i][2] = widths[i] end
  if FORMAT:match("latex") then
    tbl = tbl:walk({Str = function(value)
      if value.text == "balanced_workload" then
        return {pandoc.Str("balanced"), pandoc.Space(), pandoc.Str("workload")}
      elseif value.text == "fewest_gaps" then
        return {pandoc.Str("fewest"), pandoc.Space(), pandoc.Str("gaps")}
      end
    end})
  end
  if FORMAT:match("latex") and count >= 5 then
    return {pandoc.RawBlock("latex", "\\begingroup\\small"), tbl,
            pandoc.RawBlock("latex", "\\endgroup")}
  end
  return tbl
end
