local function score_filter(min_score, max_score, pattern, nodes)
  return function(record)
    local ts = record.ts or -1
    if ts == -1 then
      return true
    else

      if min_score ~= nil and max_score ~= nil then
        if ts < min_score or ts >= max_score then
          return false
        end
      end

      if pattern ~= nil then
        local lines = record.lines
        for i=#lines,1,-1 do
          local line = lines[i]
          if string.find(line, pattern) == nil then
            list.remove(lines, i)
          end
        end
      end

      if nodes ~= nil then
        for i=#nodes,1,-1 do
          local n = nodes[i]
          if n == record.node then
            return true
          end
        end
        return false
      end

      return true
    end
  end
end

local function pattern_filter(pattern)
  return function(record)
    for line in record.lines do
      return string.find(s, pattern) ~= nil
    end
  end
end

local function map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  m['node'] = r.node
  m['lines'] = r.lines
  m['result'] = r.result
  m['type'] = r.type
  return m
end

function score(stream, min_score, max_score, pattern, nodes)
  local s_filter = score_filter(min_score, max_score, pattern, nodes)
  local m = map()
  return stream : filter(s_filter) : map(map_record)
end
