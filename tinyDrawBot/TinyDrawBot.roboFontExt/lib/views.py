from AppKit import *
import re

from lib.scripting.PyDETextView import PyDETextView,OUTPUT_TEXT, ERROR_TEXT
from lib.scripting.scriptTools import ScriptRunner
from lib.scripting.scriptingWindow import PyTextEditor

from lib.scripting.cocoaDrawingTools import DrawingTools
import warnings

epsPasteBoardType = "CorePasteboardFlavorType 0x41494342"

variableRE = r".*^%s\s?=\s?([0-9]+)\s?$"

height_RE = re.compile(variableRE % "HEIGHT", re.MULTILINE + re.DOTALL)
width_RE = re.compile(variableRE % "WIDTH", re.MULTILINE + re.DOTALL)

size_RE = re.compile(r".*^size\s?\(\s?([0-9]+),\s?([0-9]+)\s?\)\s?$", 
                    re.MULTILINE + re.DOTALL)

class SimpleOutput(object):
    def __init__(self, dataList, isErr=False):
        self.data = dataList
        self.isErr = isErr
        
    def write(self, data):
        if isinstance(data, str):
            try:
                data = unicode(data, "utf-8", "replace")
            except UnicodeDecodeError:
                data = "XXX " + repr(data)
        self.data.append((self.isErr, data))


class TinyDrawBotDrawingTools(DrawingTools):
    
    """
    sub class of drawing tools so code writtin in DrawBot will work.
    """
    
    def __init__(self):
        super(TinyDrawBotDrawingTools, self).__init__()
        self._savePDFPath = None
    
    def saveImage(self, path):
        self._savePDFPath = path  

    saveimage = saveImage
    
class DrawView(NSView):
    def __new__(cls, *arg, **kwargs):
        self = cls.alloc().init()
        return self
    
    def __init__(self, errorView):
        self.setFrame_(NSMakeRect(0, 0, 1000, 1000))

        self._errorView = errorView
        self._code = ""
        self._runRaw = False
        self._pdfImage = None
        self._startDrag = False
        
        self._namespaces = dict()
        self._drawingTools = TinyDrawBotDrawingTools()

        for name in self._drawingTools.__all__:
            self._namespaces[name] = getattr(self._drawingTools, name)
    
    def getPath(self):
        window = self.window()
        if window is None:
            return None
        document = window.document()
        if document is None:
            return None
        url = document.fileURL()
        if url is None:
            return None
        return url.path()

    def setCode(self, code, runRaw=False):
        height, width = self.frame()[1]
        heightMath = height_RE.match(code)
        if heightMath:
            height = int(heightMath.group(1))
        
        widthMath = width_RE.match(code)
        if widthMath:
            width = int(widthMath.group(1))
        
        code = "WIDTH = %s\nHEIGHT = %s\n" %(width, height) + code
        
        self.setFrame_(NSMakeRect(0, 0, width, height))
        self._code = code
        
        self._runRaw = runRaw
        self._pdfImage = None
        self.createPDFdata()
        self.savePDF_(self._drawingTools._savePDFPath)
            
    def runCode(self):
        self._errorView.set("")
        if not self._code:    
            return
        self._drawingTools._reset()
        self.output = []
        self.stdout = SimpleOutput(self.output)
        self.stderr = SimpleOutput(self.output, True)
        path = self.getPath()
        ScriptRunner(text=self._code, path=path, stdout=self.stdout, stderr=self.stderr, namespace=self._namespaces)
        
        _st = NSMutableAttributedString.alloc().init()
        for isErr, data in self.output:
            attrs = OUTPUT_TEXT 
            if isErr:
                attrs = ERROR_TEXT
            txt = NSAttributedString.alloc().initWithString_attributes_(data, attrs)
            self._errorView.getNSTextView().textStorage().appendAttributedString_(txt)
        
        
    def createPDFdata(self):
        self._pdfImage = NSPDFImageRep.imageRepWithData_(self._pdfData)
        
    def refresh(self):
        self.setNeedsDisplay_(True)
    
    def drawRect_(self, rect):
        if self._runRaw:
            self.runCode()
            return
        if self._pdfImage is None:
            self.runCode()
        else:
            self._pdfImage.drawAtPoint_((0, 0))
            
    ### drag pdf data out :)
    def mouseDown_(self, event):
        if self._pdfImage is None:
            return
        self._startDrag = True
        
    
    def mouseDragged_(self, event):
        if self._pdfImage is None:
            return
        if not self._startDrag:
            return
            
        self.startDrag = False
        pboard = NSPasteboard.pasteboardWithName_(NSDragPboard)
        pboard.declareTypes_owner_(["com.adobe.pdf", NSPDFPboardType, NSPostScriptPboardType, NSTIFFPboardType, epsPasteBoardType], self)
        w, h = self._pdfImage.size()
        srcRect = ((0, 0), (w, h))
        if w > 400 or h > 400:
            if w > h:
                scale = 400.0 / w
            else:
                scale = 400.0 / h
            dstRect = ((0, 0), (scale * w, scale * h))
            x, y = self.convertPoint_fromView_(event.locationInWindow(), None)
            offset = x * (1 - scale), y * (1 - scale)
        else:
            dstRect = srcRect
            offset = (0, 0)
        drawImage = NSImage.alloc().initWithSize_(dstRect[1])
        drawImage.lockFocus()
        self._pdfImage.drawInRect_(dstRect)
        drawImage.unlockFocus()
        self.dragImage_at_offset_event_pasteboard_source_slideBack_(
            drawImage, offset, (0, 0), event, pboard, self, True)
    
    def pasteboard_provideDataForType_(self, pboard, _type):
        if _type == NSPDFPboardType or _type == "com.adobe.pdf":
            pboard.setData_forType_(self._pdfData, NSPDFPboardType)
        elif _type == NSPostScriptPboardType:
            pboard.setData_forType_(self._epsData, NSPostScriptPboardType)
        elif _type == NSTIFFPboardType:
            pboard.setData_forType_(self._tiffData, NSTIFFPboardType)
        elif _type == epsPasteBoardType:
            pboard.setData_forType_(self._epsData, epsPasteBoardType)


    def _get_pdfData(self):
        return self.dataWithPDFInsideRect_(((0, 0), self.frame()[1]))
    _pdfData = property(_get_pdfData)

    def _get_epsData(self):
        return self.dataWithEPSInsideRect_(((0, 0), self.frame()[1]))
    _epsData = property(_get_epsData)
    
    def _get_tiffData(self):
        self._pdfImage.size()
        im = NSImage.alloc().initWithSize_(self._pdfImage.size())
        im.lockFocus()
        self._pdfImage.drawAtPoint_((0, 0))
        im.unlockFocus()
        return im.TIFFRepresentation()
    _tiffData = property(_get_tiffData)

    def savePDF_(self, path):
        if path is not None:
            self._pdfData.writeToFile_atomically_(path , False)
    
class TinyDrawBotPyDETextView(PyDETextView):
    
    def setDrawView_(self, view):
        self._drawView = view
    
    def runPython_(self, sender):
        if hasattr(self, "_drawView"):
            self._drawView.setCode(self.string())

class TinyDrawBotTextEditor(PyTextEditor):
    
    nsTextViewClass = TinyDrawBotPyDETextView
    
    def setDrawView(self, view):
        self.getNSTextView().setDrawView_(view)
    