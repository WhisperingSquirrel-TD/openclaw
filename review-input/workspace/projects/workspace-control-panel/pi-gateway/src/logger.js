function createLogger({ subsystem = 'pi-gateway', sink = console } = {}) {
  function emit(level, event, fields = {}) {
    const entry = {
      ts: new Date().toISOString(),
      level,
      subsystem,
      event,
      ...fields
    };
    const line = JSON.stringify(entry);
    if (level === 'error') sink.error(line);
    else sink.log(line);
  }

  return {
    info(event, fields) {
      emit('info', event, fields);
    },
    warn(event, fields) {
      emit('warn', event, fields);
    },
    error(event, fields) {
      emit('error', event, fields);
    }
  };
}

module.exports = {
  createLogger
};
