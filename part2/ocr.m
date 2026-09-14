#import <Foundation/Foundation.h>
#import <Vision/Vision.h>

// Local OCR; keep boxes and confidence without correcting recognized digits.
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) return 2;
        NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]];
        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
        request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        request.usesLanguageCorrection = NO;
        request.recognitionLanguages = @[@"en-US"];
        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithURL:url options:@{}];
        NSError *error = nil;
        if (![handler performRequests:@[request] error:&error]) {
            fprintf(stderr, "OCR failed: %s\n", [[error description] UTF8String]);
            return 1;
        }
        NSMutableArray *rows = [NSMutableArray array];
        for (VNRecognizedTextObservation *observation in request.results) {
            VNRecognizedText *candidate = [[observation topCandidates:1] firstObject];
            if (!candidate) continue;
            CGRect box = observation.boundingBox;
            [rows addObject:@{@"text":candidate.string, @"confidence":@(candidate.confidence),
                             @"x":@(CGRectGetMinX(box)), @"y":@(CGRectGetMidY(box)),
                             @"height":@(CGRectGetHeight(box))}];
        }
        NSData *data = [NSJSONSerialization dataWithJSONObject:rows options:0 error:&error];
        if (!data) return 1;
        [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    }
    return 0;
}
