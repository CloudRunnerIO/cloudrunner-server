
local function simple_map_record(r)
  local m = map()
  m['id'] = r.id
  m['ts'] = r.ts
  m['uuid'] = r.uuid
  return m
end

local function content_map_record(r)
  local m = map()
  m['ts'] = r.ts
  m['node'] = r.node
  m['uuid'] = r.uuid
  m['io'] = r.io
  m['type'] = r.type
  m['lines'] = r.lines
  m['result'] = r.result
  return m
end

-- Search functions

local function org_filter(org)
  return function(record)
    return org == record.org
  end
end

local function score_filter(min, max)
  return function(record)
    if record.type == 'meta' then return true end
    return record.ts >= min and record.ts <= max
  end
end

local function node_filter(nodes)
  return function(record)
    if record.type == 'meta' then return true end
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
    if record.type == 'meta' then return true end
    return owner == record.owner
  end
end

local function uuid_filter(uuids)
  return function(record)
    if record.type == 'meta' then return true end
    for i=#uuids,1,-1 do
      local u = uuids[i]
      if u == record.uuid then
        return true
      end
    end
    return false
  end
end

local function content_filter(pattern)
  return function(record)
    if record.type == 'meta' then return true end
    local lines = record.lines
    if lines then
      for l=1,#lines do
        local line = lines[l]
        if line ~= nil and line ~= "" and string.find(line, pattern) ~= nil then
          return true
        end
      end
    end
  end
end

local function aggregate_search_results(resultMap, nextResult)
  local uuid = nextResult.uuid
  -- warn("FILTER::AGGR %s %s", uuid, nextResult.ts)
  resultMap[uuid] = (resultMap[uuid] or 0) + 1
  return resultMap
end

function search(stream, args)
  -- warn("FILTER BY: %s", tostring(args))
  local org_filter = org_filter(args.org)
  stream : filter(org_filter)

  if args.uuids ~= nil and args.uuids ~= "" then
    -- warn("FILTER BY UUIDS: %s", tostring(args.uuids))
    local u_filter = uuid_filter(args.uuids)
    stream : filter(u_filter)
  end

  if args.owner ~= nil and args.owner ~= "" then
    -- warn("FILTER BY OWNER: %s", tostring(args.owner))
    local o_filter = owner_filter(args.owner)
    stream : filter(o_filter)
  end

  if args.nodes ~= nil and args.nodes ~= "" then
    -- warn("FILTER BY NODES: %s", tostring(args.nodes))
    local n_filter = node_filter(args.nodes)
    stream : filter(n_filter)
  end

  if args.min_score ~= nil and args.min_score ~= "" then
    -- warn("FILTER BY MIN SCORE: %s : %s", tostring(args.min_score), tostring(args.max_score))
    local sc_filter = score_filter(args.min_score, args.max_score)
    stream : filter(sc_filter)
  end

  if args.pattern ~= nil and args.pattern ~= "" then
    -- warn("FILTER BY PATTERN: %s", tostring(args.pattern))
    local c_filter = content_filter(args.pattern)
    stream : filter(c_filter)
  end

  if args.full_map then
    stream : map(content_map_record)
  else
    stream : map(simple_map_record);
  end

  if args.aggregate == 1 then
    stream : aggregate(map(), aggregate_search_results)
  end

  return stream
end

local userModule = {};

function userModule.search_ids(rec, args)
  local val = rec.key
  local ts = rec.ts
  local min_score = args.marker
  local ts_min = args.start_ts
  local ts_max = args.end_ts
  if ts_min ~= nil and ts_min ~= "" and ts < ts_min then return nil end
  if ts_max ~= nil and ts_max ~= "" and ts > ts_max then return nil end
  if val >= min_score then
    return nil
  else
    return rec
  end
end

function userModule.adjust_settings( ldtMap )
  local ldt_settings=require('ldt/settings_lstack');
  ldt_settings.use_package( ldtMap, "ListMediumObject" );

  ldt_settings.set_store_limit( ldtMap, 10000 )

  ldt_settings.set_ldr_entry_count_max( ldtMap, 10000 )

  ldt_settings.set_coldlist_max( ldtMap, 200 )
  ldt_settings.set_colddir_rec_max( ldtMap, 10000 )
end

return userModule;
