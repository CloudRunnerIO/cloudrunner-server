
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
        if record.lines == nil then
          return false
        end
        local lines = record.lines
        for i=#lines,1,-1 do
          local line = lines[i]
          if line == nil or line == "" or string.find(line, pattern) == nil then
            list.remove(lines, i)
          end
        end
        record.lines = lines
        if #record.lines == 0 then
          return false
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

local function map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  m['node'] = r.node
  m['lines'] = r.lines
  m['io'] = r.io
  m['result'] = r.result
  m['type'] = r.type
  return m
end

local function simple_map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  return m
end

function score(stream, min_score, max_score, pattern, nodes)
  local s_filter = score_filter(min_score, max_score, pattern, nodes)
  return stream : filter(s_filter) : map(map_record)
end

-- Search functions

local function org_filter(org)
  return function(record)
    return org == record.org
  end
end

local function node_filter(nodes)
  return function(record)
    for i=#nodes,1,-1 do
      local n = nodes[i]
      if n == record.node then
        return true
      end
    end
    return false
  end
end

local function owner_filter(owner)
  return function(record)
    return owner == record.owner
  end
end

local userModule = {};

local function content_filter(bin, pattern)
  return function(record)
    if record[bin] == nil then return false end

    local lstack = require('ldt/lib_lstack')
    if not lstack.ldt_exists(record, bin) then return false end

    local logs = lstack.peek(record, bin, 1, 'filters', 'filter_contents', pattern)
    return #logs > 0
  end
end

function search(stream, bin, filters)
  local org_filter = org_filter(filters.org)
  stream : filter(org_filter)

  if filters.owner ~= nil and filters.owner ~= "" then
    local o_filter = owner_filter(filters.owner)
    stream : filter(o_filter)
  end

  if filters.nodes ~= nil and filters.nodes ~= "" then
    local n_filter = node_filter(filters.nodes)
    stream : filter(n_filter)
  end
  if filters.pattern ~= nil and filters.pattern ~= "" then
    local s_filter = content_filter(bin, filters.pattern)
    stream : filter(s_filter)
  end
  return stream : map(simple_map_record);
end

function userModule.search_ids(rec, min_score)
  local val = rec.key
  if val >= min_score then
    return nil
  else
    return rec
  end
end

function userModule.filter_contents(record, pattern)
  if type(record) ~= "userdata" then return false end

  local lines = record.lines
  for l=1,#lines do
    local line = lines[l]
    if line ~= nil and line ~= "" and string.find(line, pattern) ~= nil then
      return true
    end
  end
end

return userModule;
