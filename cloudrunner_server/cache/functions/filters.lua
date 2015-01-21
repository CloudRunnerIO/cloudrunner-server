
local function simple_map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  local lstack = require('ldt/lib_lstack')
  if lstack.ldt_exists(r, 'content') then
    lines = lstack.peek(r, 'content', 0)
    m['num_lines'] = #lines
  end
  return m
end

local function content_map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  m['result'] = r.result
  local lstack = require('ldt/lib_lstack')
  if lstack.ldt_exists(r, 'content') then
    lines = lstack.peek(r, 'content', 0)
    m['content'] = lines
  end
  return m
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

local function uuid_filter(uuids)
  return function(record)
    for i=#uuids,1,-1 do
      local u = uuids[i]
      if u == record.uuid then
        return true
      end
    end
    return false
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
  if filters.uuids ~= nil and filters.uuids ~= "" then
    local u_filter = uuid_filter(filters.uuids)
    stream : filter(u_filter)
  end
  if filters.full_map then
    return stream : map(content_map_record)
  else
    return stream : map(simple_map_record);
  end
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
  warn('FILTER: TYPE(%s)', type(record))
  if type(record) ~= "userdata" then return false end

  local lines = record.lines
  warn('FILTER: LINES(%s)', lines)
  if lines then
    for l=1,#lines do
      local line = lines[l]
      if line ~= nil and line ~= "" and string.find(line, pattern) ~= nil then
        return true
      end
    end
  end
end

function userModule.adjust_settings( ldtMap )
  local ldt_settings=require('ldt/settings_lstack');
  ldt_settings.use_package( ldtMap, "ListMediumObject" );

  ldt_settings.set_coldlist_max( ldtMap, 100 )
  ldt_settings.set_colddir_rec_max( ldtMap, 10000 )
end

return userModule;
