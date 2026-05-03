export default {
  main: {
    title: "ZeroTrace Engine",
    intro: "系统整理工具",
    description: "本机清理与回收工作台。先扫描、再确认、后移动。",
  },

  common: {
    buttons: {
      back: "返回",
      backToMain: "返回首页",
      browse: "浏览",
      cancel: "取消",
      clearSelection: "清除选择",
      close: "关闭",
      copy: "复制",
      copySelected: "复制",
      currentDirectory: "当前目录",
      delete: "删除",
      duplicateDetection: "重复检测",
      execute: "执行",
      export: "导出",
      language: "语言",
      moveToRecycle: "移至回收区",
      ok: "确定",
      open: "打开",
      operationFailed: "操作失败",
      permanentDelete: "永久删除",
      purge: "彻底删除",
      purgedRecords: "彻底删除记录",
      ready: "准备就绪",
      readySentence: "准备就绪。",
      refresh: "刷新",
      remove: "移除",
      restore: "恢复",
      retry: "重试",
      save: "保存",
      search: "搜索",
      select: "选择",
      selectAll: "全选",
      start: "开始",
      status: "状态",
      stop: "停止",
      targetDirectory: "目标目录",
      unstarted: "未开始",
    },

    labels: {
      csvPath: "CSV 路径",
      currentDirectory: "当前目录",
      fileName: "文件名",
      filePath: "文件路径",
      finishedAt: "结束时间",
      generatedAt: "生成时间",
      imageCount: "图片数量",
      jsonPath: "JSON 路径",
      language: "语言",
      logPath: "日志路径",
      startedAt: "开始时间",
      status: "状态",
      summary: "摘要",
      targetDirectory: "目标目录",
    },

    actions: {
      deleting: (path) => `正在删除 ${path} ...`,
      deleted: (path) => `已删除 ${path}。`,
      copying: (path) => `正在复制 ${path} ...`,
      copied: (path) => `已复制到 ${path}`,
      restoredTo: (path) => `已恢复到 ${path}`,
      purged: (path) => `已彻底删除 ${path}`,
    },
  },

  index: {
    labels: {
      recycleBin: "回收区",
      description: "本机清理与回收工作台。先扫描、再确认、后移动。",
    },
  },

  cleanup: {
    labels: {
      title: "系统整理",
      description: "扫描并清理不必要的文件，释放磁盘空间。",
    },
  },

  logs: {
    labels: {
      title: "操作日志",
      description: "查看和管理系统整理的操作日志。",
    },
  },

  recycle: {
    labels: {
      title: "回收区",
      description: "管理已删除的文件，选择恢复或永久删除。",
    },
  },

  scan: {
    labels: {
      title: "扫描结果",
      description: "查看扫描结果，选择要清理的文件。",
    },
  },

  dialog: {
    buttons: {
      cancel: "取消",
      confirm: "确认",
      ok: "确定"
    },
    title: {
      confirm: "确认操作",
      error: "操作失败",
      warning: "警告"
    }
  },

  system: {
    labels: {
      finishedAt: "结束时间",
      generatedAt: "生成时间",
      startedAt: "开始时间",
      status: "状态",
      summary: "摘要"
    }
  },
};
